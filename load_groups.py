"""Reviewable import-sequence groups anchored by source-checked load cards.

Import order is a clue only. These proposals never assign a photo, dimensions,
financial data or a template box. Same-container appearance is not identity.
"""
from pathlib import Path
from datetime import datetime,timezone
from calculator_evidence import file_digest
from photo_semantics import scores,likely_receipt,measurement_relevance
from review_assist import decode_embedding


def card_candidates(case,include_hidden=False):
    candidates=[]
    for position,record in enumerate(case.get('imported_files',[])):
        path=record['path'];row=case.get('local_photo_results',{}).get(path,{})
        if not row.get('sha256') or Path(path).suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'):continue
        from load_identity import current_clue
        values=scores(row);entry=current_clue(dict(case,load_card_dismissals={}),path,row['sha256']) or {}
        review=case.get('load_card_reviews',{}).get(path,{})
        if review.get('sha256')!=row.get('sha256'):review={}
        signal=bool(values and values['load_board']>.26 and values['load_board']>values['property']+.035)
        if signal and not review and not entry.get('options') and values['receipt']>values['load_board'] and likely_receipt(values,path):continue
        if not signal and not entry.get('options') and not entry.get('stage_reading',{}).get('stage') and not review and not (row.get('card_detector_version')==1 and (row.get('card_detected') or row.get('card_regions'))):continue
        hidden=case.get('load_card_dismissals',{}).get(path,{}).get('sha256')==row.get('sha256')
        if hidden and not include_hidden:continue
        try:
            if file_digest(path)!=row['sha256']:continue
        except OSError:continue
        candidates.append(dict(record,hidden=hidden,position=position,sha256=row['sha256'],options=entry.get('options',[]),reviewed_vendor=review.get('vendor_load') if review.get('confirmed') else None,reviewed_load=review.get('load') if review.get('confirmed') and review.get('sha256')==row['sha256'] else None,rank=values.get('load_board',0)+(1 if entry.get('options') else 0)))
    return sorted(candidates,key=lambda r:(-r['rank'],r['position']))


def confirm_card(case,path,load_number,expected_sha=None,vendor_number=None,stage=None):
    if stage not in (None,'empty','quarter','half','three_quarters','full'):raise ValueError('Choose a supported loading stage.')
    if isinstance(load_number,bool) or not isinstance(load_number,int) or not 1<=load_number<=150:raise ValueError('Enter a load number from 1 to 150.')
    if vendor_number is not None and (isinstance(vendor_number,bool) or not isinstance(vendor_number,int) or not 1<=vendor_number<=150):raise ValueError('Enter the number shown on the card, from 1 to 150.')
    if path not in {r['path'] for r in case.get('imported_files',[])}:raise ValueError('Import the original photo first.')
    row=case.get('local_photo_results',{}).get(path,{})
    digest=file_digest(path)
    if expected_sha is not None and digest!=expected_sha:raise ValueError('The card changed after its preview was opened. Inspect it again.')
    from PIL import Image
    with Image.open(path) as image:image.verify()
    if row.get('sha256')!=digest:raise ValueError('This photo changed. Inspect its current version before confirming it.')
    # UI obtains confirmation before creating the additional empty loads.
    from ed_app import default_load
    while len(case['loads'])<load_number:case['loads'].append(default_load(len(case['loads'])+1))
    case.get('load_card_dismissals',{}).pop(path,None)
    case.setdefault('load_card_reviews',{})[path]=dict(path=path,sha256=digest,load=load_number,vendor_load=vendor_number,stage=stage,confirmed=True,reviewed_at=datetime.now(timezone.utc).isoformat())


def propose_groups(case,rows):
    """Use explicit card text / bounded clocks; file order supplies no identity."""
    from evidence_groups import propose_evidence_groups
    return propose_evidence_groups(case,rows)
