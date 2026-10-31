import zipfile,tempfile,sys,csv
from pathlib import Path
from collections import Counter
from visual_intake import classify_records
base=Path('/mnt/data'); samples=[]
for zpath in sorted(base.glob('Workorder_*_Documents.zip')):
 with zipfile.ZipFile(zpath) as z:
  imgs=[i for i in z.infolist() if i.filename.lower().endswith(('.jpg','.jpeg','.png'))]
  picks=imgs[:6]+imgs[len(imgs)//2:len(imgs)//2+6]+imgs[-6:]
  with tempfile.TemporaryDirectory() as t:
   entries=[]
   for j,i in enumerate(picks):
    dest=Path(t)/f'{j}_{Path(i.filename).name}'
    with z.open(i) as src,dest.open('wb') as out:out.write(src.read())
    entries.append({'path':str(dest),'name':i.filename})
   rows=classify_records(entries)
   count=Counter(r['candidate'] for r in rows)
   samples.append({'work_order':zpath.stem.split('_')[1],'files_in_zip':len(imgs),'sampled':len(rows),**count})
with (base/'ED_v7_Visual_Triage_Test.csv').open('w',newline='') as f:
 cols=sorted(set().union(*(r.keys() for r in samples)));w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(samples)
for r in samples:print(r)
