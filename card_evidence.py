"""Literal card-stage clues and reviewed vendor-to-package mapping, not geometry."""
import re
from calculator_evidence import file_digest

def stage_claim(case,path):
    from load_identity import current_clue
    try:sha=file_digest(path)
    except OSError:return None
    if case.get('load_card_dismissals',{}).get(path,{}).get('sha256')==sha:return None
    review=case.get('load_card_reviews',{}).get(path,{})
    if review.get('confirmed') and review.get('sha256')==sha and review.get('stage') in ('empty','quarter','half','three_quarters','full'):
        from card_regions import locate_cards
        areas=[max(0,r['box'][2]-r['box'][0])*max(0,r['box'][3]-r['box'][1]) for r in locate_cards(path) if len(r.get('box',[]))==4]
        return dict(stage=review['stage'],sha256=sha,basis='Reviewed Card Text',scene_context=bool(areas and max(areas)<.25),verified=True)
    clue=current_clue(case,path,sha)
    if not clue or clue.get('status') not in ('single_reader','corroborated'):return None
    patterns={'empty':r'empty(?:\s+container)?','quarter':r'(?:1\s*/\s*4|quarter)(?:\s+full)?',
              'half':r'(?:1\s*/\s*2|half)(?:\s+full)?','three_quarters':r'(?:3\s*/\s*4|three\s+quarters?)(?:\s+full)?','full':r'full(?:\s+container)?'}
    claims=set()
    for reading in clue.get('readings',[]):
        if reading.get('incomplete'):continue
        for line in reading.get('text','').splitlines():
            value=line.strip(' .,:;').lower()
            for stage,pattern in patterns.items():
                if re.fullmatch(pattern,value):claims.add(stage)
    from card_fractions import VERSION as FRACTION_VERSION
    fractions=[r for r in clue.get('fraction_readings',[]) if r.get('version')==FRACTION_VERSION and r.get('stage')=='half' and len(r.get('box',[]))==4]
    if fractions:claims.add('half')
    if len(claims)!=1:return None
    areas=[]
    for region in clue.get('card_regions',[]):
        box=region.get('box',[])
        if len(box)==4 and all(isinstance(v,(int,float)) and 0<=v<=1 for v in box):areas.append(max(0,box[2]-box[0])*max(0,box[3]-box[1]))
    return dict(stage=next(iter(claims)),sha256=sha,basis='Standalone Fraction Shape' if fractions else 'Literal Card Text',scene_context=bool(areas and max(areas)<.25),verified=False)

def reviewed_card_mapping(case,path):
    from load_identity import current_clue
    try:sha=file_digest(path)
    except OSError:return None
    if case.get('load_card_dismissals',{}).get(path,{}).get('sha256')==sha:return None
    clue=current_clue(case,path,sha);own=case.get('load_card_reviews',{}).get(path,{})
    vendor=own.get('vendor_load') if own.get('confirmed') and own.get('sha256')==sha else None
    if vendor is None:
        if not clue or clue.get('status') not in ('single_reader','corroborated') or len(clue.get('options',[]))!=1:return None
        vendor=clue['options'][0]
    # A direct source-bound review is authoritative only for this photo.
    if own.get('confirmed') and own.get('sha256')==sha:
        target=own.get('load')
        if isinstance(target,int) and not isinstance(target,bool) and 1<=target<=len(case.get('loads',[])):return target
    targets=set();dates=set();locations=set()
    def source_date(p,digest):
        from visual_photo_review import timing_clues
        text=case.get('photo_text_cache',{}).get(p,{})
        value=timing_clues(p,(text.get('text','')+'\n'+text.get('timing_text','')) if text.get('sha256')==digest else '')
        found={c.get('date') for c in value['clues'] if c.get('date')}
        return next(iter(found)) if len(found)==1 and not value['flags'] else None
    for p in set(case.get('load_identity_cache',{})) | set(case.get('load_card_reviews',{})):
        try:
            digest=file_digest(p);reading=current_clue(case,p,digest)
            review=case.get('load_card_reviews',{}).get(p,{})
            label=review.get('vendor_load') if review.get('confirmed') and review.get('sha256')==digest else None
            matches=label==vendor or (label is None and reading and reading.get('options')==[vendor] and reading.get('status') in ('single_reader','corroborated'))
            if matches:
                date=source_date(p,digest)
                if date:dates.add(date)
                from photo_locations import photo_locations
                locations.update(v['key'] for v in photo_locations(case,p,digest))
        except (OSError,TypeError):continue
    if len(dates)>1 or len(locations)>1:return None
    for p,review in case.get('load_card_reviews',{}).items():
        if not review.get('confirmed'):continue
        try:
            digest=file_digest(p)
            if review.get('sha256')!=digest or case.get('load_card_dismissals',{}).get(p,{}).get('sha256')==digest:continue
        except OSError:continue
        anchor=current_clue(case,p,digest)
        if review.get('vendor_load')==vendor or (review.get('vendor_load') is None and anchor and anchor.get('status') in ('single_reader','corroborated') and anchor.get('options')==[vendor]):targets.add(review.get('load'))
    target=next(iter(targets)) if len(targets)==1 else None
    return target if isinstance(target,int) and not isinstance(target,bool) and 1<=target<=len(case.get('loads',[])) else None
