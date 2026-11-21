"""Bounded paper-region proposals. A region never establishes a load identity."""
import numpy as np
from PIL import Image,ImageOps
VERSION=3

def _locate_cards(path,limit=3):
    import cv2
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((800,800));rgb=np.asarray(image)
    height,width=rgb.shape[:2];hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    strokes=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,np.ones((17,17),np.uint8))
    masks=[]
    for value in (100,135,170,205):
        mask=cv2.inRange(hsv,(0,0,value),(180,100,255))
        # Remove thin overlay lettering before joining the paper surface.
        # This changes only localization masks, never source image pixels.
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
        masks.append(cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8)))
    # Printed load cards also use yellow paper. Keep the same geometric and
    # ink checks as neutral paper; color alone never establishes a load.
    yellow=cv2.inRange(hsv,(18,55,110),(40,255,255))
    yellow=cv2.morphologyEx(yellow,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    masks.append(cv2.morphologyEx(yellow,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8)))
    masks.append(cv2.morphologyEx(yellow,cv2.MORPH_CLOSE,np.ones((31,31),np.uint8)))
    edges=cv2.Canny(gray,45,130);masks.append(cv2.dilate(edges,np.ones((2,2),np.uint8)))
    candidates=[]
    for mask_index,mask in enumerate(masks):
        yellow_label=mask_index in (4,5)
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area=cv2.contourArea(contour);fraction=area/(width*height)
            if not .004<=fraction<=.55:continue
            rect=cv2.minAreaRect(contour);a,b=rect[1]
            ratio_min,ratio_max=(.12,8) if yellow_label else (.35,2.9)
            if min(a,b)<24 or not ratio_min<=a/b<=ratio_max or area/(a*b)<(.5 if yellow_label else .70):continue
            polygon=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
            if not 4<=len(polygon)<=7:continue
            x,y,w,h=cv2.boundingRect(contour)
            # Internal tonal variation is required: blank walls are not cards.
            inside=np.zeros(gray.shape,np.uint8);cv2.drawContours(inside,[contour],-1,255,-1);inside=cv2.erode(inside,np.ones((5,5),np.uint8));pixels=gray[inside>0]
            if len(pixels)<100:continue
            ink=float((strokes[inside>0]>25).mean())
            neutral=float((hsv[:,:,1][inside>0]<100).mean())
            yellow_fraction=float(((hsv[:,:,0]>=18)&(hsv[:,:,0]<=40)&(hsv[:,:,1]>=55))[inside>0].mean())
            if not .004<=ink<=(.5 if yellow_label else .28) or max(neutral,yellow_fraction)<.6:continue
            # Handwriting consists of several compact strokes, not long window
            # frames / door edges. Inspect only pixels inside the paper mask.
            letters=(((gray<130) if yellow_label else (strokes>16))&(inside>0)).astype(np.uint8)
            count,labels,stats,centroids=cv2.connectedComponentsWithStats(letters,8)
            components=0
            for sx,sy,sw,sh,sa in stats[1:]:
                max_glyph=max(w,h)*.6 if yellow_label else min(w,h)*.3
                if 3<=sh<=max_glyph and 2<=sw<=(max(w,h)*.6 if yellow_label else w*.35) and .12<=sw/sh<=8 and 5<=sa<=area*(.3 if yellow_label else .08):components+=1
            if components<(3 if yellow_label else 4):continue
            pad_x=5+round(w*.08) if yellow_label and max(w/h,h/w)>1.3 else 5
            pad_y=5+round(h*.18) if yellow_label and max(w/h,h/w)>1.3 else 5
            box=[max(0,(x-pad_x)/width),max(0,(y-pad_y)/height),min(1,(x+w+pad_x)/width),min(1,(y+h+pad_y)/height)]
            score=area/(a*b)+min(.2,ink*2)+min(.15,fraction)
            candidates.append(dict(box=box,score=round(score,6),version=VERSION))
    candidates.sort(key=lambda r:(-r['score'],r['box']))
    distinct=[]
    for row in candidates:
        x1,y1,x2,y2=row['box'];area=(x2-x1)*(y2-y1)
        duplicate=False
        for prev in distinct:
            a,b,c,d=prev['box'];overlap=max(0,min(x2,c)-max(x1,a))*max(0,min(y2,d)-max(y1,b));other=(c-a)*(d-b)
            if overlap/max(min(area,other),1e-9)>.7:duplicate=True;break
        if not duplicate:distinct.append(row)
        if len(distinct)>=limit:break
    return distinct

def card_crops(path,regions):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB')
        for region in regions:
            box=region['box'];crop=image.crop((round(box[0]*image.width),round(box[1]*image.height),round(box[2]*image.width),round(box[3]*image.height)))
            if crop.width<2 or crop.height<2:continue
            yield crop


from functools import lru_cache
from pathlib import Path
@lru_cache(maxsize=2048)
def _cached(path,size,mtime,limit):
    return tuple((tuple(r['box']),r['score'],r['version']) for r in _locate_cards(path,limit))

def locate_cards(path,limit=3):
    source=Path(path);stat=source.stat()
    return [dict(box=list(box),score=score,version=version) for box,score,version in _cached(str(source.resolve()),stat.st_size,stat.st_mtime_ns,limit)]
