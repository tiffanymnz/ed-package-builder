"""Independent relevance and stage clues from existing source-checked embeddings."""
import numpy as np
from semantic_vectors import VECTORS
from review_assist import decode_embedding

_PROTOTYPES={k:np.asarray(v,np.float32) for k,v in VECTORS.items()}
VERSION=1

def scores(row):
    vector=decode_embedding(row)
    if vector is None:return {}
    values={k:float(vector@v) for k,v in _PROTOTYPES.items()}
    return values if max(values.values())>.15 else {}

def measurement_relevance(values,geometry=None):
    if not values:return None
    positive=values['container_measurement']
    # Clear grass/bin signals are stronger than the generic tape cue. A pointing
    # hand requires a visible line cue before it can be a measurement candidate.
    if values['grass_measurement']>positive+.025:return False
    if values['bin_interior']>positive+.025:return False
    if values['load_board']>positive+.02:return False
    line=max((geometry or {}).get('horizontal',0),(geometry or {}).get('vertical',0))
    if values['pointing_hand']>positive+.015 and line<.20:return False
    return True

def stage_suggestion(values,category,row=None):
    if row is not None:
        if category != 'property_photos':return None
        vector=decode_embedding(row)
        if vector is None:return None
        from photo_stage_head import predict_stage
        result=predict_stage(vector)
        if result['stage'] is None:return None
        return dict(stage=result['stage'],basis='Visible Scene Suggestion',verified=False,head_version=result['head_version'])
    # Legacy callers without source-checked features retain their old helper.
    if not values or category!='property_photos':return None
    difference=values['before']-values['after']
    if max(values['before'],values['after'])<.26 or abs(difference)<.012:return None
    return dict(stage='before' if difference>0 else 'after',basis='Visible Scene Suggestion',verified=False)

def paper_fraction(path):
    import cv2
    from PIL import Image,ImageOps
    with Image.open(path) as image:
        image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((480,480));rgb=np.asarray(image)
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);mask=cv2.inRange(hsv,(0,0,110),(180,65,255))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    return max((cv2.contourArea(c)/(image.width*image.height) for c in contours),default=0)

def likely_receipt(values,path,purpose=None):
    if not values:return False
    if purpose is not None and not (purpose.get('receipt',0)>=.10 and purpose.get('receipt',0)>purpose.get('other',0)):return False
    return values['receipt']>.25 and values['receipt']>values['property']+.015 and values['receipt']>values['loaded_container']+.015 and values['load_board']<values['receipt']+.025 and paper_fraction(path)>.065
