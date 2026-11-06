"""Source-bound undo of explicit review actions, without reverting worker caches."""
import copy
from calculator_evidence import file_digest
KEYS=('load_sequence_anchors','photo_load_assignments','photo_category_examples','property_stage_reviews','before_photos','during_photos','after_photos')
def snapshot(case):return {k:copy.deepcopy(case.get(k)) for k in KEYS}
def remember(case,before,paths,kind):
 return dict(before=before,after=snapshot(case),sources={p:file_digest(p) for p in paths},kind=kind)
def undo(case,action):
 if not action or snapshot(case)!=action['after']:raise ValueError('Later review changes exist. Undo would overwrite them.')
 if any(file_digest(p)!=sha for p,sha in action['sources'].items()):raise ValueError('A reviewed source changed. Inspect it again before changing its assignment.')
 for key,value in action['before'].items():
  if value is None:case.pop(key,None)
  else:case[key]=copy.deepcopy(value)
def record_metric(case,kind,count):
 metric=case.setdefault('review_metrics',{}).setdefault(kind,{'batches':0,'photos':0})
 metric['batches']+=1;metric['photos']+=count
