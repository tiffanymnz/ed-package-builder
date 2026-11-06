"""Source-checked load clues and bounded sequence proposals; never assignments."""
import json,re,tempfile,time
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from calculator_evidence import file_digest
from load_text_runtime import MODEL_DIGEST,RUNTIME
from small_vision_runtime import SetupCancelled

VERSION=5
LABEL=re.compile(r'^\s*load\s*[#*:＋+«]?\s*(\d{1,3})(?![\d./])\s*[.,]?\s*$',re.I)
FOCUSED_LABEL=re.compile(r'^\s*l[oa]{2}d\s*[#*:＋+«]?\s*(\d{1,3})(?![\d./])\s*[.,]?\s*$',re.I)

def label_number(text,focused=False):
 match=(FOCUSED_LABEL if focused else LABEL).fullmatch(text)
 return int(match[1]) if match and 1<=int(match[1])<=150 else None

CIRCLED={ord(chr(0x2460+i)):str(i+1) for i in range(20)}
def text_numbers(text,focused=False):
 # Read a complete label line, including the common Truck (1) Load (2) form.
 # Do not pull numbers out of prose, invoices or dimension expressions.
 normalized=str(text).translate(CIRCLED)
 # A label on its own line followed by one integer is a bounded card layout.
 # Restrict to adjacent nonempty lines; never extract digits from dimensions.
 normalized=re.sub(r'(?im)^(\s*(?:load|truck\s*#?\s*\(?\s*\d{1,3}\s*\)?\s*[-:,]?\s*load)\s*[#*:＋+«]?)\s*\n[ \t]*(\(?\d{1,3}\)?)[ \t]*$',r'\1 \2',normalized)
 pattern=r'\s*(?:truck\s*#?\s*\(?\s*\d{1,3}\s*\)?\s*[-:,]?\s*)?l'+('[oa]{2}' if focused else 'oa')+r'd\s*[#*:＋+«]?\s*\(?\s*(\d{1,3})\s*\)?\s*[.,]?\s*'
 numbers=set()
 for line in normalized.splitlines():
  match=re.fullmatch(pattern,line,re.I)
  if match and 1<=int(match[1])<=150:numbers.add(int(match[1]))
 return sorted(numbers)

def white_label_candidate(pixels):
 import cv2
 hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV);gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
 neutral=float((hsv[:,:,1]<45).mean());edge=float((cv2.Canny(gray,40,120)>0).mean())
 return neutral>.83 and .005<edge<.12 and float(gray.mean())>85

def card_candidate(path,text='',scene_scores=None):
 from cor_package import classify_document
 if classify_document(text) in ('invoice','bid','estimate','work_order','hpir'):return False
 if text_numbers(text) or re.search(r'\b(?:load|truck|loas)\b',text,re.I):return True
 import cv2
 try:
  with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((800,800));pixels=np.asarray(im)
  scene_compatible=True  # Scene scores order work; they must not veto a visible paper card.
  if scene_compatible and white_label_candidate(pixels):return True
  from card_regions import locate_cards
  if locate_cards(path):return True
  hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV);mask=cv2.inRange(hsv,(18,55,100),(40,255,255));mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8));contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
  for contour in contours:
   x,y,w,h=cv2.boundingRect(contour);area=cv2.contourArea(contour)
   if scene_compatible and area/(im.width*im.height)>.04 and .35<w/h<1.7 and area/(w*h)>.55 and y+h>im.height*.45:return True
 except (OSError,ValueError):pass
 return False

def regions(text):
 text=text.replace('<s>','').replace('</s>','');out=[]
 for match in re.finditer(r'([^<>]+)((?:<loc_\d+>){8})',text):
  coords=list(map(int,re.findall(r'<loc_(\d+)>',match[2])));out.append(dict(text=match[1].strip(),coords=coords))
 return out

def combine_readings(readings):
 options=sorted({n for r in readings for n in r.get('loads',[])})
 engines={r['engine'] for r in readings if r.get('loads')}
 if len(options)>1:return dict(load=None,options=options,status='conflict')
 if not options:return dict(load=None,options=[],status='no_clue')
 return dict(load=options[0] if len(engines)>=2 else None,options=options,status='corroborated' if len(engines)>=2 else 'single_reader')

def read_load_card(path,base_text,cancel,runtime=None):
 from local_reader import read_image
 from card_regions import locate_cards,card_crops,VERSION as DETECTOR_VERSION
 runtime=runtime or RUNTIME;start=time.monotonic();before=file_digest(path)
 from cor_package import classify_document
 if classify_document(base_text) in ('invoice','bid','estimate','work_order','hpir'):
  return dict(sha256=before,model_digest=MODEL_DIGEST,version=VERSION,load=None,options=[],status='document',readings=[])
 readings=[dict(engine='standard',view='whole',loads=text_numbers(base_text),text=base_text[:1500])]
 detected=locate_cards(path);incomplete=False
 def read_view(image,view,max_tokens=224):
  nonlocal incomplete
  result=runtime.read(image,'regions',cancel,max_tokens=max_tokens)
  if result.get('truncated'):
   incomplete=True;readings.append(dict(engine='florence',view=view,loads=[],text=result.get('text','')[:1500],incomplete=True));return
  found=regions(result['text']);text='\n'.join(r['text'] for r in found)
  numbers=sorted({n for r in found for n in text_numbers(r['text'])})
  if classify_document(text) in ('invoice','bid','estimate','work_order','hpir'):numbers=[]
  readings.append(dict(engine='florence',view=view,loads=numbers,text=text[:1500]))
 for i,crop in enumerate(card_crops(path,detected)):
  if cancel.is_set():raise SetupCancelled()
  with tempfile.TemporaryDirectory(prefix='ed-load-card-') as folder:
   target=Path(folder)/'card.png';crop.save(target);classic,_=read_image(target,page_mode=6)
  readings.append(dict(engine='standard',view=f'card-{i}',loads=text_numbers(classic),text=classic[:1500]))
  read_view(crop,f'card-{i}')
 # A truncated whole scene no longer discards successful independent card crops.
 if not detected and not any(r['loads'] and r['engine']=='florence' for r in readings):
  read_view(path,'whole')
  # Retain the legacy independent line check when a whole scene supplies a label.
  whole=readings[-1]
  if whole.get('loads') and whole.get('view')=='whole':
   with Image.open(path) as original:
    image=ImageOps.exif_transpose(original).convert('RGB')
   line=runtime.read(image,'text',cancel,max_tokens=40)
   readings.append(dict(engine='florence',view='whole_text_check',loads=[] if line.get('truncated') else text_numbers(line.get('text','').strip(),focused=True),text=line.get('text','')[:300],incomplete=bool(line.get('truncated'))))
 if before!=file_digest(path):raise ValueError('Photo changed during load-card reading.')
 result=combine_readings(readings)
 if not result['options'] and incomplete:result['status']='incomplete'
 fractions=[]
 if result['status'] in ('single_reader','corroborated') and len(result['options'])==1:
  from card_fractions import propose_half
  for i,crop in enumerate(card_crops(path,detected)):
   if cancel.is_set():raise SetupCancelled()
   fractions.extend(dict(row,region=i) for row in propose_half(crop))
 if before!=file_digest(path):raise ValueError('Photo changed during fraction analysis.')
 return dict(result,sha256=before,model_digest=MODEL_DIGEST,version=VERSION,readings=readings,
             card_regions=detected,fraction_readings=fractions,detector_version=DETECTOR_VERSION,seconds=round(time.monotonic()-start,2))

def current_clue(case,path,sha):
 if case.get('load_card_dismissals',{}).get(path,{}).get('sha256')==sha:return None
 if any(d.get('confirmed') and d.get('path')==path and d.get('role') in ('invoice','bid','estimate','work_order','hpir') for d in case.get('package_documents',[])):return None
 entry=case.get('load_identity_cache',{}).get(path,{})
 if not sha or entry.get('sha256')!=sha or entry.get('model_digest')!=MODEL_DIGEST or entry.get('version')!=VERSION:return None
 return entry

def explicit_clock(clue):
 if clue.get('source')=='Camera Metadata':return bool(clue.get('time'))
 found=re.search(r'(?<!\d)(\d{1,2}):\d{2}(?::\d{2})?\s*\.?\s*(AM|PM)?',clue.get('value',''),re.I)
 return bool(found and (found[2] or int(found[1])==0 or int(found[1])>12))

def mark_sequence_anchor(case,row,load,kind):
 from review_assist import confirm_load_membership
 if kind not in ('start','end') or not row.get('sequence_time') or not row.get('sequence_source'):raise ValueError('This photo needs an unambiguous date and time. Date-only photos cannot define a time boundary.')
 if row.get('category') not in ('measurement','container_photos'):raise ValueError('Choose actual container/load evidence for a load boundary.')
 if row['sha256']!=file_digest(row['path']):raise ValueError('The photo changed. Inspect it again.')
 if row['path'] not in {r['path'] for r in case.get('imported_files',[])}:raise ValueError('Import the source photo first.')
 confirm_load_membership(case,[row['path']],load,{row['path']:{'sha256':row['sha256']}})
 case.setdefault('load_sequence_anchors',{})[f'{load}:{kind}']=dict(path=row['path'],sha256=row['sha256'],load=load,kind=kind)
 case['load_sequence_anchors'][f'{load}:{kind}'].update(sequence_time=row['sequence_time'],sequence_source=row['sequence_source'])

def propose_loads(case,rows):
 """Direct labels or intervals between two reviewed time anchors. No extrapolation."""
 output={};anchors={}
 for row in rows:
  path=row['path'];sha=row['sha256'];tag=case.get('photo_load_assignments',{}).get(path,{})
  reviewed=tag.get('load') if tag.get('sha256')==sha else None
  if reviewed and row.get('sequence_time') and row.get('sequence_source'):
   anchors.setdefault((reviewed,row['sequence_source']),[]).append((row['sequence_time'],path))
  clue=current_clue(case,path,sha)
  if clue:
   if clue.get('status')=='conflict':output[path]=dict(load=None,status='conflict',reason='Load Readings Disagree')
   elif clue.get('status')=='corroborated':
    from card_evidence import reviewed_card_mapping
    vendor=clue.get('load');n=reviewed_card_mapping(case,path)
    if n is not None:
     if reviewed and reviewed!=n:output[path]=dict(load=None,status='conflict',reason='Card / Reviewed Load Conflict')
     elif not reviewed:output[path]=dict(load=n,status='card',reason=f'Possible Package Load {n} · Reviewed Card Mapping')
    elif vendor and not reviewed:
     output[path]=dict(load=None,vendor_load=vendor,status='new_load' if vendor>len(case.get('loads',[])) else 'vendor_card',reason=f'Card Reads Load {vendor} · Choose Package Load')
   elif clue.get('status')=='single_reader':
    options=clue.get('options',[]);label=f'Single Reading: Load {options[0]}' if len(options)==1 else 'Single Load Reading · Check Card'
    output[path]=dict(load=None,status='single_reader',reason=label)
 valid=[];by_path={r['path']:r for r in rows}
 for n in range(1,len(case.get('loads',[]))+1):
  pair=[]
  for kind in ('start','end'):
   mark=case.get('load_sequence_anchors',{}).get(f'{n}:{kind}',{});row=by_path.get(mark.get('path'))
   if not row or mark.get('sha256')!=row['sha256'] or row.get('load')!=n or not row.get('sequence_time') or mark.get('sequence_time')!=row['sequence_time'] or mark.get('sequence_source')!=row.get('sequence_source'):break
   pair.append(row)
  if len(pair)!=2 or pair[0]['path']==pair[1]['path'] or pair[0].get('sequence_source')!=pair[1].get('sequence_source'):continue
  source=pair[0].get('sequence_source');start,end=pair[0]['sequence_time'],pair[1]['sequence_time']
  try:span=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
  except ValueError:continue
  if not 0<span<=14400:continue
  if any(other!=n and s==source and any(start<=t<=end for t,p in entries) for (other,s),entries in anchors.items()):continue
  valid.append((n,source,start,end))
 for row in rows:
  path=row['path']
  if path in output or row.get('load') or not row.get('sequence_time') or row.get('category') not in ('container_photos','measurement'):continue
  matching=[(n,start,end) for n,s,start,end in valid if s==row.get('sequence_source') and start<=row['sequence_time']<=end]
  if len({n for n,a,b in matching})==1:
   n,a,b=matching[0];output[path]=dict(load=n,status='sequence',reason=f'Possible Load {n} · Time Clue',anchors=[a,b])
 return output
