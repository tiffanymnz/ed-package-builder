"""Literal loading-stage text; fractions never establish dimensions or volume."""
import re
PATTERNS={'empty':r'empty(?:\s+container)?','quarter':r'(?:1\s*/\s*4|quarter)(?:\s*full)?','half':r'(?:1\s*/\s*2|half)(?:\s*full)?','three_quarters':r'(?:3\s*/\s*4|three[ -]+quarters?)(?:\s*full)?','full':r'full(?:\s+container)?'}
def stages(text):
 found=set()
 for line in str(text).splitlines():
  value=line.strip(' .,:;').lower().translate(str.maketrans({'¼':'1/4','½':'1/2','¾':'3/4'}))
  for stage,pattern in PATTERNS.items():
   if re.fullmatch(pattern,value):found.add(stage)
 return sorted(found)
def evidence(readings):
 values={};claims=set()
 for reading in readings:
  if reading.get('incomplete'):continue
  for stage in stages(reading.get('text','')):
   claims.add(stage);values.setdefault(stage,set()).add(reading['engine'])
 if len(claims)>1:return dict(stage=None,options=sorted(claims),status='conflict')
 if not claims:return dict(stage=None,options=[],status='none')
 stage=next(iter(claims));return dict(stage=stage,options=[stage],status='corroborated' if len(values[stage])>=2 else 'single_reader')
