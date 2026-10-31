"""Optional, opt-in local-only multimodal inference for ED evidence.
No internet endpoints, no API keys, and no auto-assignment to COR packages.
Requires a user-installed localhost Ollama vision model. Outputs are unverified.
"""
import base64, io, json, re, urllib.request, urllib.error
from pathlib import Path
from PIL import Image, ImageOps

CATEGORIES={'measurement','load_progression','dump_receipt','disposal_unloading','property_before','property_during','property_after','load_sign','other','unclear'}
STAGES={'0','25','50','75','100','unknown'}
PROMPT='''Identify the evidence in this photo for an Excessive Debris documentation package. Return ONLY one JSON object with keys: category (measurement/load_progression/dump_receipt/disposal_unloading/property_before/property_during/property_after/load_sign/other/unclear), stage (0/25/50/75/100/unknown), load_number (positive integer or null), visible_text (string), dimension_clues (string), receipt_id (string), reason (short string). Do not guess any load number or measurement not explicitly visible. Estimated fullness is a suggestion, not verification. A receipt is not proof of a specific load without identifiers.'''

def prepare_image(path, size=1024):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((size,size))
        buf=io.BytesIO();im.save(buf,format='JPEG',quality=77)
        return base64.b64encode(buf.getvalue()).decode('ascii')

def parse_response(value):
    if isinstance(value,str):
        s=value.strip();s=re.sub(r'^```(?:json)?\s*|\s*```$','',s)
        try: value=json.loads(s)
        except Exception:
            found=re.search(r'\{.*\}',s,re.S)
            if not found:raise ValueError('Model did not return parseable JSON')
            value=json.loads(found.group(0))
    if not isinstance(value,dict):raise ValueError('Model returned a non-object')
    category=str(value.get('category','unclear')).strip().lower()
    if category not in CATEGORIES:category='unclear'
    stage=str(value.get('stage','unknown')).replace('%','').strip()
    if stage not in STAGES:stage='unknown'
    try:load=int(value.get('load_number'));load=load if 1<=load<=150 else None
    except (TypeError,ValueError):load=None
    return {'category':category,'stage':stage,'load_number':load,
            'visible_text':str(value.get('visible_text') or '')[:500],
            'dimension_clues':str(value.get('dimension_clues') or '')[:250],
            'receipt_id':str(value.get('receipt_id') or '')[:100],
            'reason':str(value.get('reason') or '')[:350],
            'verified':False}

def analyze_local(path,model='llava',timeout=90):
    # Fixed loopback address prevents accidental vendor photo exfiltration.
    img=prepare_image(path)
    payload=json.dumps({'model':model,'stream':False,'prompt':PROMPT,'images':[img],'format':'json','options':{'temperature':0}}).encode()
    req=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=payload,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        data=json.load(resp)
    return parse_response(data.get('response',''))

def suggest_load_links(rows):
    """Only explicit image-visible identifiers yield load *candidates*. No assignment."""
    by_load={}
    for row in rows:
        x=row.get('prediction',{})
        if isinstance(x,dict) and x.get('load_number'):
            by_load.setdefault(x['load_number'],[]).append(row)
    return by_load
