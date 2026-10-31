"""Optional OCR review for load signs and disposal receipts.

All findings are provisional; OCR must not authorize an ED approval or load assignment.
Tesseract must be installed separately; absence degrades safely to unavailable status.
"""
from pathlib import Path
import re, csv, json, shutil, subprocess, tempfile, os
from PIL import Image, ImageOps, ImageEnhance
IMAGE_EXT={'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.webp'}


def available():
    return shutil.which('tesseract') is not None


def extract_text(path):
    if not available():
        return '', 'OCR unavailable: Tesseract is not installed; no content recognition attempted'
    try:
        with Image.open(path) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((1600,1600))
            im=ImageEnhance.Contrast(im).enhance(1.4)
            fd,tmp=tempfile.mkstemp(suffix='.png');os.close(fd)
            try:
                im.save(tmp)
                proc=subprocess.run(['tesseract',tmp,'stdout','--psm','11'],capture_output=True,text=True,timeout=15)
            finally:
                os.unlink(tmp)
        if proc.returncode!=0:
            return '', 'OCR error: '+proc.stderr.strip()[:150]
        return proc.stdout, ''
    except Exception as e:
        return '', 'OCR error: '+str(e)[:150]


def interpret(text):
    normalized=' '.join(text.upper().split())
    load=re.search(r'\bLOAD\s*[-#:]*\s*(\d{1,2})\b',normalized)
    stage=re.search(r'(?<!\d)(0|25|50|75|100)\s*%\s*(?:FULL)?',normalized)
    receipt_terms=[w for w in ['LANDFILL','SCALE TICKET','DISPOSAL','DUMP','NET WEIGHT','GROSS WEIGHT','TARE','TRANSFER STATION','WEIGHMASTER'] if w in normalized]
    dims=re.findall(r'(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(?:FT|FEET|\x27|\u2032)\b',normalized)
    case=re.search(r'\b\d{3}-\d{6}\b',normalized)
    # Receipt-like means wording found, not a confirmed disposal transaction.
    return {'load_candidate':load.group(1) if load else '',
            'stage_candidate':stage.group(1)+'%' if stage else '',
            'receipt_terms':', '.join(receipt_terms),
            'dimension_values_ft':', '.join(dims[:8]),
            'case_candidate':case.group(0) if case else ''}


def analyze(records,out_dir,limit=None):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    imgs=[r for r in records if Path(r.get('path','')).suffix.lower() in IMAGE_EXT and Path(r.get('path','')).is_file()]
    if limit is not None:imgs=imgs[:limit]
    rows=[]
    for i,r in enumerate(imgs):
        extracted,error=extract_text(r['path'])
        props=interpret(extracted)
        rows.append({'file':r.get('name',Path(r['path']).name),'path':r['path'],'source':r.get('source',''),**props,
                     'ocr_excerpt':' '.join(extracted.split())[:450], 'note':error or 'UNVERIFIED OCR suggestion; visually confirm before use'})
    if rows:
        with (out_dir/'OCR_Review_Candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out_dir/'OCR_Review_Candidates.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return rows
