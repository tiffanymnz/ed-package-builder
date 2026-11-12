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
