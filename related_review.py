"""Automatic visual review batches. Shared appearance never supplies trip identity."""
import hashlib
import numpy as np
from calculator_evidence import file_digest

def related_groups(case,rows):
 imported={r['path'] for r in case.get('imported_files',[])}
 documents={d.get('path') for d in case.get('package_documents',[]) if d.get('confirmed') and d.get('role')!='exclude'}
 families={'container_photos':'Container','property_photos':'Property','measurement':'Measurement'}
 groups=[]
 for row in sorted(rows,key=lambda r:r['sha256']):
  family=families.get(row.get('category'));vector=row.get('embedding');path=row['path']
  if not family or path not in imported or path in documents or vector is None:continue
  try:
   if file_digest(path)!=row['sha256']:continue
  except OSError:continue
  vector=np.asarray(vector,dtype=np.float32)
  if vector.shape!=(512,) or not np.isfinite(vector).all() or np.linalg.norm(vector)==0:continue
  vector=vector/np.linalg.norm(vector)
  # Every member must match the original representative: avoid visual chaining
  # that gradually merges unrelated scenes. Date is a review-batch boundary,
  # never evidence that the batch is one physical trip.
  candidates=[(float(vector@g['anchor']),g) for g in groups if g['family']==family and g['date']==row.get('sequence_date') and len(g['rows'])<48]
  candidates.sort(key=lambda x:-x[0])
  if candidates and candidates[0][0]>=.88 and (len(candidates)==1 or candidates[0][0]-candidates[1][0]>=.025):candidates[0][1]['rows'].append(row)
  else:groups.append(dict(anchor=vector,rows=[row],family=family,date=row.get('sequence_date')))
 out={};numbers={}
 for group in groups:
  if len(group['rows'])<3:continue
  family=group['family'];numbers[family]=numbers.get(family,0)+1
  key=hashlib.sha256('|'.join(r['sha256'] for r in group['rows']).encode()).hexdigest()[:12]
  label=f"Similar {family} Views {numbers[family]}"
  for r in group['rows']:
   if r.get('load') or r.get('stage') in ('before','during','after'):continue
   out[r['path']]=dict(group_id='visual-review:'+key,group_label=label,load=None,review_only=True,verified=False,basis='Similar Visible Content; Check Trip and Stage')
 return out
