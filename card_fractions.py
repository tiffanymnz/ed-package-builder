"""Standalone handwritten half-fraction shape proposals; never reinterpret plain 12."""
import numpy as np

VERSION=1

def half_candidates(image):
    import cv2
    rgb=np.asarray(image.convert('RGB'));height,width=rgb.shape[:2]
    if min(height,width)<60:return []
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    ink=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,np.ones((19,19),np.uint8))
    mask=(ink>30).astype(np.uint8)*255
    # Reconnect a broken vertical fraction stroke, without joining side-by-side digits.
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((max(3,round(height*.012)),1),np.uint8))
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(mask,8)
    parts=[]
    for index,(x,y,w,h,area) in enumerate(stats[1:],1):
        if area<6 or y<height*.25 or y+h>height*.78 or h<height*.035:continue
        parts.append(dict(index=index,x=int(x),y=int(y),w=int(w),h=int(h)))
    results=[]
    for bar in parts:
        if bar['w']/bar['h']>.22 or bar['h']<height*.10:continue
        for top in parts:
            if top is bar or not .05<=top['w']/top['h']<=.45:continue
            if not 1.7<=bar['h']/top['h']<=3.5:continue
            gap=bar['x']-(top['x']+top['w'])
            if not 0<=gap<=top['h']*.8 or abs(top['y']-bar['y'])>top['h']*.4:continue
            for bottom in parts:
                if bottom is bar or bottom is top:continue
                if not .6<=bottom['w']/bottom['h']<=2.5 or not .5<=bottom['h']/top['h']<=1.4:continue
                if not 0<=bottom['x']-(bar['x']+bar['w'])<=top['h']*.8:continue
                if not .45<=((bottom['y']-top['y'])/top['h'])<=1.8:continue
                if bottom['y']+bottom['h']>bar['y']+bar['h']+top['h']*.2:continue
                x1=top['x'];y1=min(top['y'],bar['y']);x2=bottom['x']+bottom['w'];y2=bar['y']+bar['h']
                if x2-x1>width*.5:continue
                # The fraction must be isolated, rather than a slice of an equation.
                pad=max(2,round(top['h']*.3));region=labels[max(0,y1-pad):min(height,y2+pad),max(0,x1-pad):min(width,x2+pad)]
                other=set(np.unique(region))-{0,top['index'],bar['index'],bottom['index']}
                if any(stats[i,4]>=6 for i in other):continue
                nearby=[i for i,(sx,sy,sw,sh,area) in enumerate(stats) if i not in (0,top['index'],bar['index'],bottom['index']) and area>=4 and sh>=3 and sx>width*.04 and sx+sw<width*.96 and sy<y2+pad and sy+sh>y1-pad]
                if nearby:continue
                glyph=(labels[bottom['y']:bottom['y']+bottom['h'],bottom['x']:bottom['x']+bottom['w']]==bottom['index'])
                results.append(dict(glyph=glyph,box=[x1/width,y1/height,x2/width,y2/height]))
    return results[:2]

def two_shape(glyph):
    """A descending middle stroke and rising baseline tail; abstain on other digits."""
    h,w=glyph.shape
    if h<8 or w<8:return False
    ys,xs=np.nonzero(glyph)
    if len(xs)<12:return False
    right=ys[xs>=w*.85];bottom=xs[ys>=h*.85]
    if not len(right) or not len(bottom):return False
    if not .45<=float(np.median(right)/h)<=.85 or float(np.median(bottom)/w)>=.48:return False
    def left(start,end):
        band=glyph[round(h*start):max(round(h*start)+1,round(h*end))]
        values=[np.flatnonzero(row)[0] for row in band if row.any()]
        return float(np.median(values)) if values else None
    top_spans=[np.flatnonzero(row)[-1]-np.flatnonzero(row)[0]+1 for row in glyph[:max(1,round(h*.25))] if row.any()]
    if not top_spans or max(top_spans)>w*.80:return False
    upper=left(.25,.40);lower=left(.50,.65)
    if upper is None or lower is None or upper-lower<w*.05:return False
    spans=[np.flatnonzero(row)[-1]-np.flatnonzero(row)[0]+1 for row in glyph[round(h*.45):] if row.any()]
    return bool(spans and max(spans)>=w*.65)

def propose_half(image):
    return [dict(stage='half',basis='Standalone Fraction Shape',box=c['box'],version=VERSION,verified=False)
            for c in half_candidates(image) if two_shape(c['glyph'])]
