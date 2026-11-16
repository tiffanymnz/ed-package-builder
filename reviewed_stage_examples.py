"""Case-local suggestions from source-checked human examples; never auto-confirm."""
import numpy as np
from visual_photo_review import current_stage
from template_review import pixel_digest
from functools import lru_cache
@lru_cache(maxsize=1024)
def _pixels(path,sha256):
    return pixel_digest(path)

def suggest_stages(case,rows,threshold=.90,margin=.06):
    anchors={};conflicts=set();pixels={}
    for row in rows:
        stage=current_stage(case,row['path'])
        if stage not in ('before','during','after') or row.get('embedding') is None:continue
        digest=_pixels(row['path'],row['sha256']);pixels[row['path']]=digest
        prior=anchors.setdefault(digest,[]);prior.append((stage,row))
        if len({s for s,_ in prior})>1:conflicts.add(digest)
    representatives=[items[0] for digest,items in anchors.items() if digest not in conflicts]
    # With only one known stage there is no useful competing comparison.
    if len({stage for stage,_ in representatives})<2:return {}
    output={}
    for row in rows:
        if row.get('category')!='property_photos' or row.get('embedding') is None or current_stage(case,row['path'])!='review':continue
        scores={};sources={}
        for stage,anchor in representatives:
            similarity=float(np.dot(row['embedding'],anchor['embedding']))
            if similarity>scores.get(stage,-1):scores[stage]=similarity;sources[stage]=anchor['path']
        ordered=sorted(scores,key=lambda stage:scores[stage],reverse=True)
        best=ordered[0]
        if scores[best]<threshold or scores[best]-scores[ordered[1]]<margin:continue
        digest=_pixels(row['path'],row['sha256'])
        if digest in conflicts:continue
        output[row['path']]=dict(stage=best,basis='Similar to Your Reviewed Photos',verified=False,
                                example_path=sources[best],similarity=round(scores[best],4))
    return output
