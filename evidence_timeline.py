"""Safe, scalable evidence sequence candidates; does NOT verify loads or classifications.
Uses EXIF dates when present, approximate image signatures, and stable file order.
Never mixes distinct work orders, and never assigns evidence to COR slots automatically.
"""
import csv, json, hashlib, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from PIL import Image, ImageOps

EXT={'.jpg','.jpeg','.png','.webp','.tiff','.tif','.bmp'}

def fingerprint(path):
    with Image.open(path) as im:
        exif=im.getexif()
        dt=str(exif.get(36867) or exif.get(306) or '').strip()
        rgb=ImageOps.exif_transpose(im).convert('RGB')
        rgb.thumbnail((256,256))
        gray=rgb.resize((9,8)).convert('L')
        px=list(gray.getdata())
        value=0
        for row in range(8):
            for col in range(8):
                value=(value<<1) | int(px[row*9+col]<px[row*9+col+1])
        return value,dt,rgb.size

def parse_date(dt):
    try:return datetime.strptime(dt,'%Y:%m:%d %H:%M:%S')
    except (TypeError,ValueError):return None

def cluster_near_duplicates(rows,max_distance=3):
    """Simple locality sensitive index via 8 hash-byte buckets; confirm visually."""
    index=defaultdict(list)
    for i,r in enumerate(rows):
        h=r.get('_hash')
        if h is None:continue
        matches=set()
        for shift in range(0,64,8):
            matches.update(index[(shift,(h>>shift)&255)][-100:])
        candidates=[]
        for j in matches:
            if (h ^ rows[j]['_hash']).bit_count()<=max_distance:candidates.append(j)
        if candidates:
            nearest=min(candidates,key=lambda j:(h ^ rows[j]['_hash']).bit_count())
            r['possible_repeat_of']=rows[nearest]['file']
            r['repeat_hamming_distance']=(h ^ rows[nearest]['_hash']).bit_count()
        for shift in range(0,64,8):index[(shift,(h>>shift)&255)].append(i)

def make_report(records,out_dir):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list);failed=[]
    for r in records:
        p=Path(r['path']);source=str(r.get('source',''))
        # The app's case is one property; do not merge separate case folders as a shortcut.
        if p.suffix.lower() not in EXT:continue
        if not p.is_file():failed.append({'file':p.name,'reason':'File missing'});continue
        try:
            h,stamp,dim=fingerprint(p)
            item=dict(file=p.name,path=str(p),source=source,exif_datetime=stamp,sequence_group='',possible_repeat_of='',repeat_hamming_distance='',review_note='',work_order=str(r.get('work_order') or r.get('case_number') or 'current_case'),_hash=h,_date=parse_date(stamp))
            groups[str(r.get('work_order') or r.get('case_number') or 'current_case')].append(item)
        except Exception as exc:failed.append({'file':p.name,'reason':str(exc)})
    result=[]; group_summary={}
    for name,items in groups.items():
        # Photos with timestamps first, then unknown timestamps in stable import order; unknowns NEVER assumed chronological.
        dated=sorted((x for x in items if x['_date'] is not None),key=lambda x:x['_date'])
        undated=[x for x in items if x['_date'] is None]
        ordered=dated+undated
        batch=0;last=None
        for x in ordered:
            if x['_date'] is None:
                x['sequence_group']='Date unavailable';x['review_note']='Timestamp unavailable: do not infer load order'
            else:
                if last is None or (x['_date']-last).total_seconds()>30*60:batch+=1
                x['sequence_group']=f'Time cluster {batch} (NOT a load)';x['review_note']='Temporal proximity does not establish load identity'
                last=x['_date']
        cluster_near_duplicates(ordered)
        result.extend(ordered)
        group_summary[name]={'photos':len(items),'dated':len(dated),'undated':len(undated),'time_clusters':batch,'potential_repeat_images':sum(bool(x['possible_repeat_of']) for x in ordered)}
    fields=['file','path','source','work_order','exif_datetime','sequence_group','possible_repeat_of','repeat_hamming_distance','review_note']
    with (out/'Evidence_Timeline.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        w=csv.DictWriter(fh,fieldnames=fields);w.writeheader()
        for x in result:
            w.writerow({k:x.get(k,'') for k in fields})
    summary={'photos_analyzed':len(result),'groups':group_summary,'unreadable_files':failed[:100], 'limitations':['Time clusters are NOT verified loads.','Possible repeats are NOT confirmed duplicates.','Images without capture EXIF are not assigned chronology.','Receipt and load-stage recognition require a validated vision model.','No automatic insertion into the COR package.']}
    (out/'Evidence_Timeline_Summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return result,summary
