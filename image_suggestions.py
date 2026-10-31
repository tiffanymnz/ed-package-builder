"""Offline, transparent visual candidate scoring, not a trained vision model.
Never converts predictions to verified load slots or reimbursement evidence.
"""
from pathlib import Path
import csv,json,math
from collections import Counter,defaultdict
import numpy as np
from PIL import Image,ImageOps,ImageFilter
import cv2
from ground_truth_review import read_rows

def describe(path):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((480,480))
        a=np.asarray(im)
        h,w=a.shape[:2]
        hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV)
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
        canny=cv2.Canny(gray,75,160)
        white=float(np.mean((hsv[:,:,1]<52)&(hsv[:,:,2]>185)))
        edges=float(np.mean(canny>0))
        yellow=float(np.mean((hsv[:,:,0]>=16)&(hsv[:,:,0]<=38)&(hsv[:,:,1]>95)&(hsv[:,:,2]>95)))
        dark=float(np.mean(gray<65))
        small=cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA)
        dhash=(small[:,1:]>small[:,:-1]).ravel()
        hist=cv2.calcHist([hsv],[0,1],None,[12,8],[0,180,0,256]);cv2.normalize(hist,hist)
        return dict(white=white,edges=edges,yellow=yellow,dark=dark,hash=''.join('1' if b else '0' for b in dhash),hist=hist.flatten())

def guess(info):
    # Narrow, auditable heuristics. Unclassified is the normal answer.
    if info['white']>.66 and info['edges']>.045:
        return 'Invoice / bid / other document','Possible paper document based on brightness and edge structure; cannot distinguish invoice from receipt', 'low'
    if info['yellow']>.17 and info['edges']>.075:
        return 'Container measurement','Possible measuring tape based on yellow pixel proportion; verify image', 'low'
    return 'Unclassified','No reliable image-only evidence type detected','none'

def candidates(labels_csv,out_dir):
    labels_csv=Path(labels_csv);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    rows=read_rows(labels_csv); desc=[]; results=[]
    for i,row in enumerate(rows):
        path=labels_csv.parent/row['thumbnail']
        try:
            inf=describe(path)
            kind,reason,certainty=guess(inf)
        except Exception as e:
            inf=None;kind,reason,certainty='Unclassified',str(e),'none'
        desc.append(inf)
        results.append(dict(id=row['id'],work_order=row['work_order'],predicted_category=kind,confidence=certainty,reason=reason,nearest_images='',exact_visual_matches='',review_priority='normal'))
    for i,r in enumerate(results):
        f=desc[i]
        if f is None:continue
        neighbors=[]; exact=[]
        for j,g in enumerate(desc):
            if i==j or g is None or results[j]['work_order']!=r['work_order']:continue
            d=sum(a!=b for a,b in zip(f['hash'],g['hash']))
            if d<=4:exact.append(results[j]['id'])
            histdist=float(cv2.compareHist(f['hist'].astype('float32'),g['hist'].astype('float32'),cv2.HISTCMP_BHATTACHARYYA))
            neighbors.append((d/64+histdist,j))
        neighbors.sort()
        r['nearest_images']='; '.join(results[j]['id'] for _,j in neighbors[:4])
        r['exact_visual_matches']='; '.join(exact[:8])
        if exact:r['review_priority']='high — possible repeat image'
        elif r['confidence']=='low':r['review_priority']='high — weak category suggestion'
        else:r['review_priority']='normal — unclassified'
    fields=['id','work_order','predicted_category','confidence','reason','nearest_images','exact_visual_matches','review_priority']
    with (out/'predictions.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows(results)
    report={'total':len(results),'by_work_order':dict(Counter(x['work_order'] for x in results)), 'predictions':dict(Counter(x['predicted_category'] for x in results)),'high_priority':sum(r['review_priority'].startswith('high') for r in results),'human_verified_accuracy':None,'warnings':['Heuristic predictions only. No class accuracy can be claimed until human labels are completed.','Only images from same work order are compared. Similarity is not evidence of same load.']}
    (out/'suggestions_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
