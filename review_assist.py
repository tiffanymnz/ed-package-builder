"""Review assistance: conservative repeat groups and unverified example matches."""
import base64
import hashlib
import math
import re
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

FEATURE_VERSION=1
PHASES={'before':'before_photos','during':'during_photos','after':'after_photos'}
STAGE_LABELS={'before':'Before Removal','during':'Removal in Progress','after':'After Removal'}
CATEGORY_LABELS={'property_photos':'Property / Debris','container_photos':'Container / Load',
                 'measurement':'Measurement','documents':'Document / Receipt','other':'Other'}

def confirm_categories(case,paths,category,rows):
    """Remember only explicit, source-checked object labels for this case."""
    from calculator_evidence import file_digest
    from datetime import datetime,timezone
    if category not in CATEGORY_LABELS:raise ValueError('Choose a photo category.')
    prepared=[]
    for path in dict.fromkeys(paths):
        digest=file_digest(path);row=rows.get(path,{})
        if row.get('sha256')!=digest:raise ValueError('A selected photo changed. Refresh the review before categorizing it.')
        try:
            with Image.open(path) as image:image.verify()
        except OSError as exc:raise ValueError('A selected image cannot be opened. Check the original photo.') from exc
        prepared.append((path,dict(category=category,sha256=digest,model_digest=row.get('model_digest'),
                                   reviewed_at=datetime.now(timezone.utc).isoformat())))
    for path,entry in prepared:case.setdefault('photo_category_examples',{})[path]=entry

def category_matches(records,rows,case):
    """Supplement abstentions with nearby, reviewed examples. No stage inference."""
    labels={};vectors={path:decode_embedding(row) for path,row in rows.items()}
    for path,entry in case.get('photo_category_examples',{}).items():
        row=rows.get(path,{})
        if entry.get('category') in CATEGORY_LABELS and row.get('sha256') and entry.get('sha256')==row['sha256']:
            labels.setdefault(path,set()).add(entry['category'])
    for path,entry in case.get('property_stage_reviews',{}).items():
        row=rows.get(path,{})
        if entry.get('visual_confirmed') and entry.get('stage') in PHASES and row.get('sha256') and entry.get('sha256')==row['sha256']:
            labels.setdefault(path,set()).add('property_photos')
    digest_labels={}
    for path,types in labels.items():digest_labels.setdefault(rows[path]['sha256'],set()).update(types)
    for path in labels:labels[path]=set(digest_labels[rows[path]['sha256']])
    anchors={}
    for path,types in labels.items():
        if len(types)==1 and vectors.get(path) is not None:anchors.setdefault(next(iter(types)),[]).append(vectors[path])
    output={}
    for record in records:
        path=record['path'];base=rows.get(path,{}).get('prediction',{}).get('category')
        entry=dict(category=base or 'not_analyzed',basis='Photo Sorter',proposed=None)
        if len(labels.get(path,set()))>1:entry.update(category='unclear',basis='Category Conflict')
        elif path in labels:entry.update(category=next(iter(labels[path])),basis='Reviewed Category')
        elif len(anchors)>=2 and vectors.get(path) is not None:
            matches=_match(vectors[path],anchors,threshold=.80,margin=.04)
            if len(matches)==1:
                proposed=matches[0]
                if base=='unclear':entry.update(category=proposed,basis='From Your Examples',proposed=proposed)
                elif base and base!=proposed:entry.update(category='unclear',basis='Category Conflict',proposed=proposed)
        output[path]=entry
    return output

def encode_embedding(vector):
    value=np.asarray(vector,np.float32);norm=float(np.linalg.norm(value))
    if value.shape!=(512,) or not np.isfinite(value).all() or norm<=0:raise ValueError('Invalid image embedding')
    return base64.b64encode((value/norm).astype('<f2').tobytes()).decode('ascii')

def decode_embedding(row):
    try:
        raw=row.get('prediction',{}).get('embedding','')
        value=np.frombuffer(base64.b64decode(raw,validate=True),dtype='<f2').astype(np.float32)
        norm=float(np.linalg.norm(value))
        if value.shape!=(512,) or not np.isfinite(value).all() or norm<=0:return None
        return value/norm
    except (TypeError,ValueError):return None

def similar_views(anchor,rows,threshold=.80):
    """Rank related views only. Similarity never establishes load or stage."""
    vector=decode_embedding(rows.get(anchor,{}))
    if vector is None:return {}
    result={}
    for path,row in rows.items():
        other=decode_embedding(row)
        if other is None:continue
        score=float(np.dot(vector,other))
        if score>=threshold:result[path]=score
    return dict(sorted(result.items(),key=lambda item:(-item[1],item[0])))

def image_features(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB');width,height=image.size
        pixels=hashlib.sha256(f'{width}x{height}:'.encode()+image.tobytes()).hexdigest()
        gray=np.asarray(image.resize((17,16),Image.Resampling.LANCZOS).convert('L'),np.int16)
        bits=gray[:,1:]>gray[:,:-1]
        dhash=f'{int.from_bytes(np.packbits(bits).tobytes(),"big"):064x}'
        tone=np.asarray(image.resize((16,16),Image.Resampling.BILINEAR),np.uint8)
        preview=np.asarray(image.resize((256,256),Image.Resampling.BILINEAR).convert('L'),np.float32)
        sharp=float(np.var(np.diff(preview,axis=0))+np.var(np.diff(preview,axis=1)))
        clipping=float(np.mean((preview<4)|(preview>251)))
        quality=round(math.log1p(sharp)+.08*math.log1p(width*height)-2*clipping,4)
    return dict(version=FEATURE_VERSION,pixel_hash=pixels,dhash=dhash,tone=base64.b64encode(tone.tobytes()).decode('ascii'),
                aspect=round(width/max(1,height),5),detail=round(float(np.std(preview)),3),quality=quality,width=width,height=height)

def near_repeat(a,b):
    # Only the grouping caller permits this for classified property/container
    # photos. Tiny text changes in documents or measurements must stay visible.
    if min(a.get('detail',0),b.get('detail',0))<10:return False
    if abs(a['aspect']-b['aspect'])>max(a['aspect'],b['aspect'])*.01:return False
    if (int(a['dhash'],16)^int(b['dhash'],16)).bit_count()>4:return False
    left=np.frombuffer(base64.b64decode(a['tone']),np.uint8).astype(np.int16)
    right=np.frombuffer(base64.b64decode(b['tone']),np.uint8).astype(np.int16)
    return left.shape==right.shape and float(np.mean(np.abs(left-right)))<=3

def valid_features(feature):
    try:
        return (feature.get('version')==FEATURE_VERSION and len(feature['pixel_hash'])==64
                and len(feature['dhash'])==64 and int(feature['dhash'],16)>=0
                and len(base64.b64decode(feature['tone'],validate=True))==768
                and all(math.isfinite(float(feature[key])) for key in ('aspect','detail','quality')))
    except (KeyError,TypeError,ValueError):return False

def used_paths(case):
    paths=set()
    for phase in PHASES.values():paths.update(case.get(phase,[]))
    for record in case.get('package_documents',[]):paths.add(record.get('path',''))
    paths.update(case.get('photo_load_assignments',{}))
    for load in case.get('loads',[]):
        paths.update(load.get('photos',{}).values());paths.update(load.get('extra_measurement_photos',[]))
        paths.update([load.get('disposal_photo',''),load.get('evidence_first_10_cyd',''),load.get('calculator_evidence',{}).get('path','')])
    return paths

def repeat_groups(records,rows,case):
    groups=[];pixel_index={};buckets={};pinned=used_paths(case)
    for record in sorted(records,key=lambda r:r['path']):
        path=record['path'];row=rows.get(path,{});feature=row.get('features',{})
        if not valid_features(feature):continue
        category=row.get('prediction',{}).get('category')
        found=pixel_index.get(feature['pixel_hash'])
        if found is None and category in ('property_photos','container_photos'):
            possible=set()
            for band in range(8):possible.update(buckets.get((category,band,feature['dhash'][band*8:(band+1)*8]),[]))
            for index in sorted(possible):
                if near_repeat(feature,groups[index]['seed']):found=index;break
        if found is None:
            found=len(groups);groups.append(dict(id='Set '+str(found+1),members=[],seed=feature))
            if category in ('property_photos','container_photos') and feature['detail']>=10:
                for band in range(8):buckets.setdefault((category,band,feature['dhash'][band*8:(band+1)*8]),[]).append(found)
        groups[found]['members'].append(path);pixel_index[feature['pixel_hash']]=found
    index={};keep=set()
    for group in groups:
        members=group['members'];best=max(members,key=lambda p:(rows[p]['features']['quality'],p))
        chosen=set(members)&pinned or {best};keep.update(chosen)
        for path in members:index[path]=dict(id=group['id'],count=len(members),recommended=path in chosen,best=best)
    return dict(index=index,keep=keep,groups=groups)

def visible_load_numbers(text):
    # Filenames and dates are deliberately not inputs.
    return sorted({int(value) for value in re.findall(r'\bload\s*(?:number|no\.?|#|:)?\s*(\d{1,3})\b',text,re.I) if 1<=int(value)<=150})

def _match(vector,anchors,threshold=.94,margin=.03):
    if vector is None:return []
    scores={label:max(float(np.dot(vector,anchor)) for anchor in values) for label,values in anchors.items() if values}
    if not scores:return []
    ordered=sorted(scores.items(),key=lambda item:item[1],reverse=True)
    if ordered[0][1]<threshold:return []
    if len(ordered)>1 and ordered[0][1]-ordered[1][1]<margin:
        return [label for label,score in ordered if ordered[0][1]-score<margin]
    return [ordered[0][0]]

def match_examples(records,rows,case):
    vectors={path:decode_embedding(row) for path,row in rows.items()}
    load_anchors={};stage_anchors={};manual_loads={}
    for path,assignment in case.get('photo_load_assignments',{}).items():
        n=assignment.get('load')
        if isinstance(n,int) and 1<=n<=len(case.get('loads',[])) and assignment.get('sha256')==rows.get(path,{}).get('sha256'):
            manual_loads.setdefault(path,set()).add(n)
            vector=vectors.get(path)
            if vector is not None:load_anchors.setdefault(n,[]).append(vector)
    for n,load in enumerate(case.get('loads',[]),1):
        for path in list(load.get('photos',{}).values())+[load.get('disposal_photo',''),load.get('evidence_first_10_cyd','')]:
            manual_loads.setdefault(path,set()).add(n)
            vector=vectors.get(path)
            if vector is not None:load_anchors.setdefault(n,[]).append(vector)
    for stage,phase in PHASES.items():
        for path in case.get(phase,[]):
            review=case.get('property_stage_reviews',{}).get(path,{})
            vector=vectors.get(path)
            if review.get('visual_confirmed') and review.get('stage')==stage and review.get('sha256')==rows.get(path,{}).get('sha256') and vector is not None:
                stage_anchors.setdefault(stage,[]).append(vector)
    output={}
    for record in records:
        path=record['path'];row=rows.get(path,{});cached=case.get('photo_text_cache',{}).get(path,{})
        numbers=visible_load_numbers(cached.get('text','')) if row.get('sha256') and cached.get('sha256')==row.get('sha256') else []
        vector=vectors.get(path);assigned=sorted(manual_loads.get(path,set()))
        conflict=bool(assigned and numbers and set(assigned)!=set(numbers))
        if conflict:loads=sorted(set(assigned+numbers));basis='Assigned Load Conflicts With Visible Text'
        elif assigned:loads=assigned;basis='Assigned Photo'
        elif numbers:loads=numbers;basis='Visible Text — Check Original'
        else:loads=_match(vector,load_anchors);basis='Visual Match — Container May Be Reused' if loads else 'No Load Clue'
        missing=any(n>len(case.get('loads',[])) for n in loads)
        if conflict:load_group='Conflicting Load Clues'
        elif not loads:load_group='No Load Clue'
        elif missing:load_group='Load Not Added Yet'
        elif len(loads)>1:load_group='Multiple Possible Loads'
        else:load_group=f'Possible Load {loads[0]}'
        category=case.get('photo_category_examples',{}).get(path,{})
        non_property=category.get('sha256')==row.get('sha256') and category.get('category') not in (None,'property_photos')
        stages=_match(vector,stage_anchors) if row.get('prediction',{}).get('category')=='property_photos' and not non_property else []
        stage=stages[0] if len(stages)==1 else None
        output[path]=dict(loads=loads,load_group=load_group,load_basis=basis,stage=stage,
                          stage_group=STAGE_LABELS.get(stage,'Stage Needs Review'),stage_basis='Similar to a Confirmed Example' if stage else 'No Clear Example Match')
    return output

def build_review_index(records,rows,case):
    return dict(repeats=repeat_groups(records,rows,case),matches=match_examples(records,rows,case),categories=category_matches(records,rows,case))

def checked_rows(records,rows,model_digest=None,prompt_version=None):
    from calculator_evidence import file_digest
    result={}
    for record in records:
        path=record['path'];row=rows.get(path,{})
        if not row.get('sha256'):continue
        try:
            if row['sha256']!=file_digest(path):continue
        except OSError:continue
        copied=dict(row)
        if model_digest is not None and (row.get('model_digest')!=model_digest or row.get('prompt_version')!=prompt_version):copied.pop('prediction',None)
        result[path]=copied
    return result

def confirm_load_membership(case,paths,load_number,rows):
    from calculator_evidence import file_digest
    from datetime import datetime,timezone
    if not isinstance(load_number,int) or not 1<=load_number<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
    prepared=[]
    for path in dict.fromkeys(paths):
        for n,load in enumerate(case['loads'],1):
            if n!=load_number and path in list(load.get('photos',{}).values())+[load.get('disposal_photo',''),load.get('evidence_first_10_cyd','')]:
                raise ValueError('A selected photo is already used as evidence for another load. Review that assignment first.')
        digest=file_digest(path)
        if rows.get(path,{}).get('sha256')!=digest:raise ValueError('A selected photo changed. Refresh the review before assigning it.')
        prepared.append((path,digest))
    for path,digest in prepared:
        case.setdefault('photo_load_assignments',{})[path]=dict(load=load_number,sha256=digest,confirmed_at=datetime.now(timezone.utc).isoformat())
