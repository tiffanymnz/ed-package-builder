"""Case-local visual neighbors. Suggestions only, never evidence/approval decisions."""
from pathlib import Path
import numpy as np
import cv2
from PIL import Image,ImageOps

EXT={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}

def image_signature(path):
    with Image.open(path) as im:
        a=np.array(ImageOps.exif_transpose(im).convert('RGB').resize((160,120)))
    hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV)
    hist=cv2.calcHist([hsv],[0,1],None,[20,10],[0,180,0,256]).flatten()
    hist=hist/(np.linalg.norm(hist)+1e-9)
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
    tiny=cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA)
    bits=(tiny[:,1:]>tiny[:,:-1]).ravel()
    h=sum(int(x)<<i for i,x in enumerate(bits))
    return hist,h

def rank_similar(selected, records, limit=15):
    """Return ranked image candidate paths, excluding source; no automatic classification."""
    base=Path(selected).resolve(); sig=image_signature(base)
    out=[]
    for row in records:
        p=Path(row['path']).resolve()
        if p==base or p.suffix.lower() not in EXT or not p.is_file():continue
        try:
            hist,h=image_signature(p)
            histogram_similarity=float(np.dot(sig[0],hist))
            distance=(sig[1]^h).bit_count()
            # Use broad ranking only. Photos with similar colors need not be same load.
            score=0.65*histogram_similarity+0.35*(1-distance/64)
            out.append(dict(path=str(p),name=p.name,score=round(score,3),hash_distance=distance,possible_repeat=distance<=3))
        except Exception:continue
    out.sort(key=lambda x:(-x['score'],x['hash_distance']))
    return out[:limit]
