"""Derived OCR views of visible ink. These views never assign a load or trip."""
import re
import numpy as np
from PIL import Image,ImageOps

def explicit_hash_load(text,score):
    if score<.90:return None
    match=re.fullmatch(r'\s*load\s*#\s*(\d{1,3})\s*',str(text),re.I)
    return int(match[1]) if match and 1<=int(match[1])<=150 else None

def retry_has_signal(image,text):
    if len(re.sub(r'\W','',str(text)))>=4:return True
    import cv2
    preview=image.convert('RGB');preview.thumbnail((400,400))
    hsv=cv2.cvtColor(np.asarray(preview),cv2.COLOR_RGB2HSV)
    return float(((hsv[:,:,0]>=18)&(hsv[:,:,0]<=40)&(hsv[:,:,1]>=55)).mean())>.20

def header_views(image):
    """Bounded retries for portrait card headings and sideways label strips."""
    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1600,1600));w,h=image.size
    if min(w,h)<24 or float(np.asarray(image.convert('L')).std())<8:return []
    views=[]
    if h>w*.8:
        for fraction in (.35,.55):
            crop=image.crop((0,0,w,max(24,round(h*fraction))))
            if np.asarray(crop.convert('L')).std()>8:views.append(('header-'+str(fraction),crop))
    if h>w*1.1:
        views.extend([('rotate-90',image.rotate(90,expand=True)),('rotate-270',image.rotate(270,expand=True))])
    return views

def text_region_view(image,coords):
    """Rectify one observed text quadrilateral, including nearby source ink."""
    import cv2
    image=ImageOps.exif_transpose(image).convert('RGB');w,h=image.size
    if len(coords)!=8:return None
    points=np.asarray(coords,np.float32).reshape(4,2)
    if not np.isfinite(points).all() or np.any(points<0) or np.any(points>1000):return None
    points[:,0]*=w/1000;points[:,1]*=h/1000
    if abs(float(cv2.contourArea(points)))<4:return None
    width=max(np.linalg.norm(points[1]-points[0]),np.linalg.norm(points[2]-points[3]))
    height=max(np.linalg.norm(points[3]-points[0]),np.linalg.norm(points[2]-points[1]))
    if min(width,height)<4 or width/height<.5 or width/height>25:return None
    center=points.mean(axis=0);points=center+(points-center)*1.18
    width=max(24,round(width*1.18));height=max(16,round(height*1.18))
    if width*height>w*h*.8:return None
    scale=min(1,1600/max(width,height));width=max(1,round(width*scale));height=max(1,round(height*scale))
    target=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],np.float32)
    transform=cv2.getPerspectiveTransform(points,target)
    return Image.fromarray(cv2.warpPerspective(np.asarray(image),transform,(width,height),borderMode=cv2.BORDER_REPLICATE))

def stage_word(text,score):
    """Bounded OCR typography in one complete word, never load-number repair."""
    if not np.isfinite(score) or score<.75:return None
    value=str(text).strip()
    if re.fullmatch(r'fu[l!i1|]{2}',value,re.I):return 'full'
    if value.lower()=='empty':return 'empty'
    return None

def stage_word_readings(image,reader):
    """Read isolated stage words twice; preserve nearby fraction ink as a veto.

    This yields single-reader review clues only. It never infers a fraction,
    assigns a load, or fills a template. At most eight small line reads and two
    verification reads are attempted on a copy bounded to 1600 pixels.
    """
    import cv2
    source=ImageOps.exif_transpose(image).convert('RGB');source.thumbnail((1600,1600));w,h=source.size
    if min(w,h)<24:return []
    gray=np.asarray(source.convert('L'))
    mask=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,51,15)
    pad=max(2,round(min(w,h)*.03));mask[:pad]=0;mask[-pad:]=0;mask[:,:pad]=0;mask[:,-pad:]=0
    kernel=np.ones((max(2,round(h*.018)),max(5,round(w*.07))),np.uint8)
    contours,_=cv2.findContours(cv2.dilate(mask,kernel),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=sorted((cv2.boundingRect(c) for c in contours),key=lambda b:b[1])
    output=[];checked=0;verifications=0
    for x,y,a,b in boxes:
        if not (a>w*.12 and 6<=b<h*.4 and a/b>.6):continue
        crop=source.crop((max(0,x-pad),max(0,y-pad),min(w,x+a+pad),min(h,y+b+pad)))
        reading=reader.read(crop);checked+=1
        if checked>=8 and not reading:break
        stage=stage_word(reading.get('text',''),reading.get('score',0)) if reading else None
        if stage and verifications<2:
            # A separate numerator/slash to the left can change Full to 1/4
            # Full. An isolated-word read must never discard that source ink.
            band=mask[max(0,y-round(b*.4)):min(h,y+b+round(b*.4)),:max(0,x-pad)]
            _,_,parts,_=cv2.connectedComponentsWithStats(band,8) if band.size else (0,None,np.empty((0,5)),None)
            nearby=any(area>=max(5,a*b*.015) and b*.3<=ph<=b*1.6 and pw<a*.9 for px,py,pw,ph,area in parts[1:])
            if not nearby:
                extra=max(3,round(b*.2));verify=source.crop((max(0,x-extra),max(0,y-extra),min(w,x+a+extra),min(h,y+b+extra)))
                second=reader.read(verify);verifications+=1
                if second and stage_word(second.get('text',''),second.get('score',0))==stage:
                    output.append(dict(engine='compact_handwriting',view='stage-word',loads=[],text='Full' if stage=='full' else 'Empty',source_text=reading['text'],score=min(reading['score'],second['score'])))
        if checked>=8 or len(output)>=2:break
    return output
