"""Independent source-file and reuse audit for ED case manifests.

This is a deterministic audit, NOT photo recognition, authenticity verification or approval.
"""
from pathlib import Path
from collections import defaultdict
import json, csv, hashlib

REQUIRED = ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt')

def reviewed_source_conflicts(case):
    from calculator_evidence import file_digest
    issues=[]
    for record in case.get('template_photo_reviews',{}).values():
        try:
            n=int(record['load']);slot=record['slot']
            if n<1:continue
            load=case['loads'][n-1]
            current=load.get('disposal_photo') if slot=='disposal_photo' else load.get('evidence_first_10_cyd') if slot=='first_10_proof' else load.get('photos',{}).get(slot)
            if not current:continue
            unchanged=Path(current).resolve()==Path(record.get('path','')).resolve() and record.get('sha256')==file_digest(current)
        except (OSError,ValueError,KeyError,IndexError,TypeError):unchanged=False
        if not unchanged:issues.append(dict(severity='BLOCKING',load=record.get('load',0),type='changed_reviewed_source',detail=f"Load {record.get('load','?')}: {record.get('slot','photo').replace('_',' ')} changed after review. Inspect the current photo."))
    return issues

def loading_photo_conflicts(case):
    from template_review import pixel_digest
    groups=defaultdict(list);cache={};issues=[]
    for n,load in enumerate(case.get('loads',[]),1):
        for slot in ('empty','quarter','half','three_quarters','full_1','full_2'):
            path=load.get('photos',{}).get(slot)
            if not path:continue
            try:
                if path not in cache:cache[path]=pixel_digest(path)
                groups[cache[path]].append((n,slot))
            except (OSError,ValueError):continue
    for uses in groups.values():
        if len(uses)>1:issues.append(dict(severity='BLOCKING',load=','.join(map(str,sorted({n for n,_ in uses}))),type='loading_stage_reuse',detail='One photograph is used for multiple loading stages or loads: '+', '.join(f'Load {n} {slot.replace("_"," ")}' for n,slot in uses)+'. Choose separate evidence.'))
    return issues

def reviewed_shared_dimension(case,entries,digest):
    places=[(path,n,slot) for path,uses in entries for n,slot in uses if n>0]
    axes={slot for _,_,slot in places}
    if len(axes)!=1 or not axes<={'height','width','length'}:return False
    unreviewed=set()
    for path,n,slot in places:
        row=case.get('shared_container_measurements',{}).get(f'{n}:{slot}',{})
        valid=row.get('container_match_confirmed') and row.get('sha256')==digest and row.get('slot')==slot and row.get('load')==n
        try:valid=valid and Path(row.get('path','')).resolve()==Path(path).resolve()
        except (OSError,ValueError):valid=False
        if not valid:unreviewed.add(n)
    return len(unreviewed)<=1


def collect(case):
    usages=defaultdict(list)
    issues=[]
    for i,load in enumerate(case.get('loads', []),1):
        from load_requirements import applicable
        for slot in REQUIRED:
            if not applicable(load,slot) and not load.get('photos',{}).get(slot):continue
            path=load.get('photos',{}).get(slot,'')
            if not path:
                issues.append({'severity':'BLOCKING','load':i,'type':'missing_slot','detail':f'Missing {slot}'})
            else:usages[str(Path(path).expanduser().resolve())].append((i,slot))
        for slot,key in [('disposal_photo','disposal_photo'),('first_10_proof','evidence_first_10_cyd')]:
            path=load.get(key,'')
            if path:usages[str(Path(path).expanduser().resolve())].append((i,slot))
            elif slot=='disposal_photo':issues.append({'severity':'BLOCKING','load':i,'type':'missing_disposal','detail':'Missing disposal/unloading image'})
        for j,p in enumerate(load.get('extra_measurement_photos',[]),1):
            if p:usages[str(Path(p).expanduser().resolve())].append((i,f'extra_measurement_{j}'))
    for slot in ('before_photos','during_photos','after_photos','financial_pdfs'):
        for j,p in enumerate(case.get(slot,[]),1):
            if p:usages[str(Path(p).expanduser().resolve())].append((0,f'{slot}_{j}'))
    sha_map=defaultdict(list)
    for path,places in usages.items():
        p=Path(path)
        if not p.is_file():
            issues.append({'severity':'BLOCKING','load':places[0][0],'type':'file_missing','detail':f'Assigned source missing: {p.name} ({places})'})
        else:
            # Hash only files selected for final package, not thousands of raw photos.
            h=hashlib.sha256()
            with p.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            sha_map[h.hexdigest()].append((path,places))
        load_ids={i for i,_ in places if i>0}
        if len(load_ids)>1 and not (p.is_file() and reviewed_shared_dimension(case,[(path,places)],hashlib.sha256(p.read_bytes()).hexdigest())):
            issues.append({'severity':'BLOCKING','load':','.join(map(str,sorted(load_ids))),'type':'cross_load_reuse','detail':f'Same file assigned to different loads: {p.name} ({places})'})
        if len(places)>1 and len(load_ids)<=1:
            issues.append({'severity':'REVIEW','load':next(iter(load_ids),0),'type':'repeated_slot','detail':f'Same file used for multiple slots: {p.name} ({places})'})
    for digest,entries in sha_map.items():
        if len(entries)<2:continue
        load_ids={i for _,places in entries for i,_ in places if i>0}
        if len(load_ids)>1 and not reviewed_shared_dimension(case,entries,digest):
            issues.append({'severity':'BLOCKING','load':','.join(map(str,sorted(load_ids))),'type':'identical_content_cross_load','detail':f'Byte-identical photos assigned across loads: '+', '.join(Path(p).name for p,_ in entries)})
    issues.extend(loading_photo_conflicts(case));issues.extend(reviewed_source_conflicts(case))
    return {'work_order':case.get('work_order',''),'case_number':case.get('case_number',''),'loads':len(case.get('loads',[])),'assigned_unique_paths':len(usages),'issues':issues,'blocking':sum(i['severity']=='BLOCKING' for i in issues),'review':sum(i['severity']=='REVIEW' for i in issues),'note':'Checks file existence and exact-byte reuse, not photo validity. Similar photos and incorrect load stages still need human verification.'}

def write_report(case,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result=collect(case)
    (output/'Evidence_Audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (output/'Evidence_Audit.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['severity','load','type','detail']);w.writeheader();w.writerows(result['issues'])
    return result
