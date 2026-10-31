"""Conservative, offline image-content triage. All results are CANDIDATES, never evidence verification."""
from pathlib import Path
from collections import Counter
import csv,json,math
import numpy as np
import cv2
from PIL import Image, ImageOps
from visual_gallery import feature,distance

EXT={'.jpg','.jpeg','.png','.tif','.tiff','.webp','.bmp'}

def inspect_image(path):
    """Fast thumbnail-level visual descriptors. No OCR, no claim of load/fullness recognition."""
    try:
        with Image.open(path) as src:
            img=ImageOps.exif_transpose(src).convert('RGB')
            img.thumbnail((500,500))
            a=np.asarray(img)
        h,w=a.shape[:2]
        hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV)
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
        # Pale, low-saturation documents are *possible* receipts, never confirmed.
        pale=np.mean((hsv[:,:,1]<68)&(hsv[:,:,2]>160))
        edges=cv2.Canny(gray,75,160)
        edensity=float((edges>0).mean())
        yellow=float(np.mean((hsv[:,:,0]>=16)&(hsv[:,:,0]<=40)&(hsv[:,:,1]>=90)&(hsv[:,:,2]>=90)))
        paper=(pale>.58 and edensity>.03)
        if paper: label='Document / receipt candidate'
        elif yellow>.11: label='Yellow-object / measurement candidate'
        else: label='General photograph — unclassified'
        return {'visual_candidate':label,'pale_fraction':round(float(pale),3),
                'yellow_fraction':round(yellow,3),'edge_density':round(edensity,3),
                'visual_reason':'Thumbnail appearance only; inspect image to confirm','feature':feature(path)}
    except Exception as e:
        return {'visual_candidate':'Unreadable image','visual_reason':str(e),'feature':None}

def classify_records(records):
    results=[]
    for rec in records:
        path=Path(rec['path'])
        if path.suffix.lower() not in EXT or not path.is_file():continue
        x=inspect_image(path)
        results.append({'file':rec.get('name',path.name),'path':str(path),'source':rec.get('source',''),
                        'candidate':x['visual_candidate'],'reason':x['visual_reason'],
                        'pale_fraction':x.get('pale_fraction',''),'yellow_fraction':x.get('yellow_fraction',''),
                        'feature':x.get('feature')})
    # Neighbor suggestions are visual, not load assignments. Restrict to small neighbor windows for scale.
    for i,row in enumerate(results):
        f=row['feature']; neighbors=[]
        if f:
            lo=max(0,i-25); hi=min(len(results),i+26)
            for j in range(lo,hi):
                other=results[j]['feature']
                if i!=j and other:
                    neighbors.append((distance(f,other),j))
        neighbors.sort()
        row['nearby_similar_files']=[results[j]['file'] for _,j in neighbors[:3]]
    for row in results:
        del row['feature']
    return results

def export(case,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    records=classify_records(case.get('imported_files',[]))
    (folder/'Visual_Review_Candidates.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    with (folder/'Visual_Review_Candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['file','candidate','reason','nearby_similar_files','pale_fraction','yellow_fraction','source','path']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in records:writer.writerow({k:', '.join(row[k]) if isinstance(row.get(k),list) else row.get(k,'') for k in fields})
    counts=dict(Counter(r['candidate'] for r in records))
    (folder/'Visual_Review_Summary.json').write_text(json.dumps({'total_images':len(records),'candidates':counts,'verified_assignments':0},indent=2),encoding='utf-8')
    return records,counts
