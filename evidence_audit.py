"""Independent source-file and reuse audit for ED case manifests.

This is a deterministic audit, NOT photo recognition, authenticity verification or approval.
"""
from pathlib import Path
from collections import defaultdict
import json, csv, hashlib

REQUIRED = ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt')

def collect(case):
    usages=defaultdict(list)
    issues=[]
    for i,load in enumerate(case.get('loads', []),1):
        for slot in REQUIRED:
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
        if len(load_ids)>1:
            issues.append({'severity':'BLOCKING','load':','.join(map(str,sorted(load_ids))),'type':'cross_load_reuse','detail':f'Same file assigned to different loads: {p.name} ({places})'})
        if len(places)>1 and len(load_ids)<=1:
            issues.append({'severity':'REVIEW','load':next(iter(load_ids),0),'type':'repeated_slot','detail':f'Same file used for multiple slots: {p.name} ({places})'})
    for digest,entries in sha_map.items():
        if len(entries)<2:continue
        load_ids={i for _,places in entries for i,_ in places if i>0}
        if len(load_ids)>1:
            issues.append({'severity':'BLOCKING','load':','.join(map(str,sorted(load_ids))),'type':'identical_content_cross_load','detail':f'Byte-identical photos assigned across loads: '+', '.join(Path(p).name for p,_ in entries)})
    return {'work_order':case.get('work_order',''),'case_number':case.get('case_number',''),'loads':len(case.get('loads',[])),'assigned_unique_paths':len(usages),'issues':issues,'blocking':sum(i['severity']=='BLOCKING' for i in issues),'review':sum(i['severity']=='REVIEW' for i in issues),'note':'Checks file existence and exact-byte reuse, not photo validity. Similar photos and incorrect load stages still need human verification.'}

def write_report(case,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result=collect(case)
    (output/'Evidence_Audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (output/'Evidence_Audit.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['severity','load','type','detail']);w.writeheader();w.writerows(result['issues'])
    return result
