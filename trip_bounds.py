"""Checked trip endpoints organize review; time alone never fills a template."""
import copy
from datetime import datetime
from calculator_evidence import file_digest

def confirm_trip_bounds(case,rows,load):
 if len(rows)!=2 or rows[0]['path']==rows[1]['path']:raise ValueError('Select the first and last photo of one physical trip.')
 if not 1<=load<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
 rows=sorted(rows,key=lambda r:r.get('sequence_time') or '')
 if not all(r.get('sequence_time') and r.get('sequence_source') in ('camera','photo_text') for r in rows) or rows[0]['sequence_source']!=rows[1]['sequence_source']:raise ValueError('Both endpoints need a date and explicit time from the same source. Date-only photos cannot establish a trip window.')
 span=(datetime.fromisoformat(rows[1]['sequence_time'])-datetime.fromisoformat(rows[0]['sequence_time'])).total_seconds()
 if not 0<span<=14400:raise ValueError('The trip window must be ordered and no longer than four hours.')
 for r in rows:
  if file_digest(r['path'])!=r['sha256']:raise ValueError('An endpoint photo changed. Inspect it again.')
 prepared=copy.deepcopy(case)
 from review_assist import confirm_categories
 from load_identity import mark_sequence_anchor
 confirm_categories(prepared,[r['path'] for r in rows],'container_photos',{r['path']:{'sha256':r['sha256']} for r in rows})
 for kind,r in zip(('start','end'),rows):mark_sequence_anchor(prepared,dict(r,category='container_photos'),load,kind)
 for r in rows:
  if file_digest(r['path'])!=r['sha256']:raise ValueError('An endpoint changed during review.')
 case.clear();case.update(prepared)

def review_windows(case,rows):
 by_path={r['path']:r for r in rows};windows=[]
 for load in range(1,len(case.get('loads',[]))+1):
  pair=[]
  for kind in ('start','end'):
   mark=case.get('load_sequence_anchors',{}).get(f'{load}:{kind}',{});r=by_path.get(mark.get('path'))
   if not r or r.get('load')!=load or not r.get('sequence_time') or any(mark.get(k)!=r.get(k) for k in ('sha256','sequence_time','sequence_source')):break
   pair.append(r)
  if len(pair)!=2 or pair[0]['sequence_source']!=pair[1]['sequence_source']:continue
  a,b=pair;span=(datetime.fromisoformat(b['sequence_time'])-datetime.fromisoformat(a['sequence_time'])).total_seconds()
  foreign=any(r.get('load') and r['load']!=load and r.get('sequence_source')==a['sequence_source'] and r.get('sequence_time') and a['sequence_time']<=r['sequence_time']<=b['sequence_time'] for r in rows)
  if 0<span<=14400 and not foreign:windows.append((load,a['sequence_source'],a['sequence_time'],b['sequence_time']))
 out={}
 for r in rows:
  if r.get('load') or r.get('stage')!='review' or r.get('category') not in ('container_photos','measurement','other') or not r.get('sequence_time'):continue
  matches=[n for n,s,a,b in windows if s==r.get('sequence_source') and a<=r['sequence_time']<=b]
  if len(matches)==1:
   n=matches[0];out[r['path']]=dict(load=None,candidate_load=n,review_only=True,verified=False,status='trip_window_review',group_label=f'Trip {n} · Review Time Window',reason=f'Check Trip {n} · Time Window Only')
 return out
