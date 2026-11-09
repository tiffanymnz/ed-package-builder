"""Propose large handwritten annotation regions above embedded scene photos.

Derived crops affect recognition only; originals and measured volumes are untouched.
"""
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
VERSION=1

def _panel(path):
 import cv2
 with Image.open(path) as source:
  im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((900,1200));rgb=np.asarray(im)
 h,w=rgb.shape[:2]
 if not .4<=w/h<=.9 or h<250:return None
 hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
 white=(hsv[:,:,1]<40)&(hsv[:,:,2]>225);fraction=white.mean(axis=1);color=((hsv[:,:,1]>25)&(hsv[:,:,2]>60)).mean(axis=1)
 if white[round(h*.16):round(h*.38)].mean()<.72:return None
 if (hsv[round(h*.65):,:,1]>35).mean()<.12:return None
 boundary=None;band=max(8,round(h*.02))
 for y in range(round(h*.30),round(h*.70)):
  if fraction[y-band:y].mean()>.76 and (fraction[y:y+band].mean()<.56 or color[y:y+band].mean()>.12):
   boundary=y;break
 if boundary is None:return None
 top=round(h*.18);mask=(gray[top:boundary]<115).astype(np.uint8)
 count,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
 glyphs=[(x,y+top,a,b) for x,y,a,b,area in stats[1:] if b>=h*.055 and area>=20 and a<w*.8 and x>w*.04 and x+a<w*.96]
 if not glyphs:return None
 x1=min(x for x,y,a,b in glyphs);y1=min(y for x,y,a,b in glyphs);x2=max(x+a for x,y,a,b in glyphs);y2=max(y+b for x,y,a,b in glyphs)
 if x2-x1>w*.85 or y2-y1<h*.06:return None
 pad=max(8,round((y2-y1)*.15))
 box=[max(0,(x1-pad)/w),max(0,(y1-pad)/h),min(1,(x2+pad)/w),min(1,(y2+pad)/h)]
 return dict(box=box,photo_box=[0,boundary/h,1,1],version=VERSION,kind='annotation_panel')

@lru_cache(maxsize=2048)
def _cached(path,size,mtime):return _panel(path)
def annotation_panel(path):
 p=Path(path);stat=p.stat();result=_cached(str(p.resolve()),stat.st_size,stat.st_mtime_ns)
 return dict(result) if result else None

def linearize_fraction(image):
 """Align three visible glyphs around an isolated diagonal fraction slash.

No glyph is added or replaced. Plain adjacent numbers cannot pass the slash
geometry check, and recognition still decides which digits are present.
 """
 import cv2
 gray=np.asarray(image.convert('L'));h,w=gray.shape;mask=(gray<115).astype(np.uint8)
 count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
 parts=[(i,tuple(map(int,s))) for i,s in enumerate(stats[1:],1) if s[4]>=20 and s[3]>=h*.15]
 if len(parts)!=3:return None
 parts.sort(key=lambda p:p[1][0]);left,slash,right=parts
 x,y,a,b,area=slash[1];ys,xs=np.nonzero(labels==slash[0])
 if len(xs)<10 or not .2<a/b<1.2 or float(np.corrcoef(xs,ys)[0,1])>-.9:return None
 if not (left[1][0]+left[1][2]<=x+a*.4 and right[1][0]>=x+a*.6):return None
 if left[1][3]>b*1.15 or right[1][3]>b*1.4:return None
 glyphs=[]
 for ident,(x,y,a,b,area) in parts:
  crop=Image.fromarray(np.where(labels[y:y+b,x:x+a]==ident,0,255).astype('uint8')).convert('RGB');crop=crop.resize((max(5,round(a*80/b)),80),Image.Resampling.LANCZOS);glyphs.append(crop)
 result=Image.new('RGB',(sum(im.width for im in glyphs)+48,104),'white');x=12
 for glyph in glyphs:result.paste(glyph,(x,12));x+=glyph.width+12
 return result
