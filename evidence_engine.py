"""Offline conservative evidence triage. Generates suggestions, never silently assigns.
No OCR or computer vision model is bundled. Textual hints and metadata only.
"""
from pathlib import Path
import re, json, hashlib, csv
from datetime import datetime
from collections import defaultdict
from PIL import Image, ImageOps

IMAGE_EXT={'.jpg','.jpeg','.png','.tif','.tiff','.webp','.bmp'}

LABELS={
 'height':r'height|depth|high', 'width':r'width|wide', 'length':r'length|long',
 'empty':r'empty|(?<!\d)0\s*percent|(?<!\d)0\s*pct|^0$',
 'quarter':r'(?:1\s*/\s*4|¼|quarter|25\s*%?|25pct)',
 'half':r'(?:1\s*/\s*2|½|half|50\s*%?|50pct)',
 'three_quarters':r'(?:3\s*/\s*4|¾|three.?quarter|75\s*%?|75pct)',
 'full_1':r'(?:100\s*%?|100pct|full|complete|loaded)',
 'receipt':r'(?:dump|landfill|disposal|tip|weigh|scale)[-_ ]*(?:receipt|ticket)|receipt|ticket',
 'disposal_photo':r'unload|dumping|disposal.?photo',
 'before_photos':r'before|prior|prework',
 'during_photos':r'during|loading|remov(?:e|ing)|progress',
 'after_photos':r'after|cleared|cleaned|postwork',
 'first_10_proof':r'first[-_ ]*10|10[-_ ]*cyd|firstten',
}
LOAD_RE = re.compile(r'(?<![a-z0-9])(?:load|trip|haul)[\s_#-]*0*([1-9]\d{0,2})(?!\d)',re.I)


def _date(path):
 try:
  with Image.open(path) as im:
   exif=im.getexif()
   for k in (36867,36868,306):
    if exif.get(k):return str(exif[k])
 except Exception:pass
 return ''

def _fingerprint(path):
 try:
  with Image.open(path) as im:
   im=ImageOps.exif_transpose(im).convert('L').resize((8,8))
   pix=list(im.getdata());mean=sum(pix)/len(pix)
   return ''.join('1' if x>=mean else '0' for x in pix)
 except Exception:return ''

def analyze(case):
 items=case.get('imported_files',[])
 out=[];grouped=defaultdict(list)
 for entry in items:
  path=Path(entry['path']);name=entry.get('name',path.name)
  if not path.is_file():continue
  stem=path.stem.lower().replace('_',' ').replace('-',' ')
  # Filename can be useful, but doesn't verify an image's content.
  hit=LOAD_RE.search(stem)
  load=int(hit.group(1)) if hit else None
  labels=[key for key,expr in LABELS.items() if re.search(expr,stem,re.I)]
  isimage=path.suffix.lower() in IMAGE_EXT
  timestamp=_date(path) if isimage else ''
  fingerprint=_fingerprint(path) if isimage else ''
  if fingerprint:grouped[fingerprint].append(name)
  pdf_text=''
  if path.suffix.lower()=='.pdf':
   try:
    import fitz
    with fitz.open(path) as doc:
     pdf_text=' '.join(page.get_text() for page in list(doc)[:2])[:1500]
   except Exception:pass
  doc_hints=[]
  if pdf_text:
   for kind,pattern in [('invoice',r'\binvoice\b'),('bid',r'\bbid\b|estimate'),('receipt',r'landfill|solid waste|disposal receipt')]:
    if re.search(pattern,pdf_text,re.I):doc_hints.append(kind)
  if len(labels)==1 and load is not None and 1<=load<=len(case.get('loads',[])):
   confidence='medium';reason='Filename explicitly describes a load and category; verify photo content'
  elif labels or load or doc_hints:
   confidence='low';reason='Partial filename/document-text clue; review manually'
  else:
   confidence='unclassified';reason='No reliable textual clue; visual review required'
  out.append({'file':name,'path':str(path),'type':path.suffix.lower(),'suggested_load':load,
   'suggested_slots':labels,'document_hints':doc_hints,'confidence':confidence,'reason':reason,
   'exif_datetime':timestamp,'visual_fingerprint':fingerprint,'possible_visual_duplicate':False})
 for row in out:
  if row['visual_fingerprint'] and len(grouped[row['visual_fingerprint']])>1:
   row['possible_visual_duplicate']=True
 # Perceptual hashing is only a review flag, not proof of a duplicated load.
 return out

def export(case,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 rows=analyze(case)
 (folder/'Photo_Triage_Suggestions.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
 with (folder/'Photo_Triage_Suggestions.csv').open('w',newline='',encoding='utf-8-sig') as f:
  fields=['file','type','suggested_load','suggested_slots','document_hints','confidence','reason','exif_datetime','possible_visual_duplicate','path']
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for row in rows:
   writer.writerow({k:', '.join(row[k]) if isinstance(row.get(k),list) else row.get(k,'') for k in fields})
 summary={'files_analyzed':len(rows),'partially_labeled':sum(bool(r['suggested_slots'] or r['suggested_load']) for r in rows),'unclassified':sum(r['confidence']=='unclassified' for r in rows),'possible_near_duplicates':sum(r['possible_visual_duplicate'] for r in rows)}
 (folder/'Photo_Triage_Summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 return rows,summary
