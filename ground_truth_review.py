"""Human-in-the-loop evaluation set builder. No label is inferred or treated as verified."""
import csv, json, hashlib, random, zipfile, io
from pathlib import Path
from collections import Counter, defaultdict
from PIL import Image, ImageOps, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

CATEGORIES = ['Unreviewed','Property before','Property during','Property after','Empty container 0%','Load 25%','Load 50%','Load 75%','Load 100%','Container measurement','Overage measurement','Dump receipt','Disposal / unloading','Whiteboard / load identifier','Invoice / bid / other document','Other / unusable','Unclear']
VALID_IMG = ('.jpg','.jpeg','.png','.webp','.tif','.tiff','.bmp')

def sample_archives(paths, output, per_archive=24, seed=1701):
    """Reproducible position-stratified sample; archives stay separate. No AI labels."""
    output=Path(output); outimg=output/'thumbnails';outimg.mkdir(parents=True,exist_ok=True)
    rows=[]
    for zp in sorted(map(Path,paths)):
        with zipfile.ZipFile(zp) as z:
            members=[m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith(VALID_IMG) and m.file_size<=25_000_000]
            # Sample across file order and seeded jitter, not only the beginning.
            rng=random.Random(seed+int(hashlib.sha256(zp.stem.encode()).hexdigest()[:8],16))
            n=min(per_archive,len(members))
            indices=[]
            for i in range(n):
                lo=(i*len(members))//n; hi=((i+1)*len(members))//n
                indices.append(rng.randrange(lo,max(lo+1,hi)))
            for k,index in enumerate(indices):
                m=members[index]; key=f'{zp.stem}_{index:05d}'
                try:
                    raw=z.read(m)
                    with Image.open(io.BytesIO(raw)) as src:
                        thumb=ImageOps.exif_transpose(src).convert('RGB');thumb.thumbnail((960,720))
                        imgpath=outimg/(key+'.jpg');thumb.save(imgpath,quality=85)
                    rows.append(dict(id=key,work_order=zp.stem.split('_')[1],archive=zp.name,original_name=m.filename,original_index=index,sha256=hashlib.sha256(raw).hexdigest(),thumbnail=str(imgpath.relative_to(output)),category='Unreviewed',load_number='',notes='',reviewer='',reviewed_at=''))
                except Exception:
                    continue
    save_rows(output/'labels.csv',rows)
    (output/'READ_ME.txt').write_text('Human labeling set. Original archives are unchanged. Label each photo; do not assume filenames are accurate. Load_number only when directly supported. Unclear is an acceptable label. No automatic load-stage or receipt claims are verified by this dataset until human review.\n',encoding='utf-8')
    return rows

def save_rows(file,rows):
    file=Path(file);file.parent.mkdir(parents=True,exist_ok=True)
    fields=['id','work_order','archive','original_name','original_index','sha256','thumbnail','category','load_number','notes','reviewer','reviewed_at']
    with file.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def read_rows(file):
    with Path(file).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def evaluate(labeled_csv, prediction_csv, output_csv=None):
    """Only score human-reviewed rows with matched IDs. Unknown is not an accuracy success."""
    labels=read_rows(labeled_csv); preds=read_rows(prediction_csv)
    lookup={r.get('id'):r for r in preds}
    matched=[]; confusion=Counter();per_cat=defaultdict(lambda:[0,0]);missing=0
    for r in labels:
        truth=r['category']
        if truth in ('Unreviewed','Unclear','') :continue
        p=lookup.get(r['id'])
        if not p:missing+=1; continue
        predicted=p.get('predicted_category','Unclassified')
        matched.append((r['id'],truth,predicted))
        confusion[(truth,predicted)]+=1
        per_cat[truth][1]+=1
        if truth==predicted:per_cat[truth][0]+=1
    accuracy=sum(t==p for _,t,p in matched)/len(matched) if matched else None
    report={'human_labeled':sum(r['category'] not in ('Unreviewed','Unclear','') for r in labels),'evaluated':len(matched),'missing_predictions':missing,'accuracy':accuracy,'per_category':{c:{'correct':a,'total':b} for c,(a,b) in per_cat.items()},'confusion':[{ 'true':a,'predicted':b,'count':n} for (a,b),n in confusion.items()]}
    if output_csv:Path(output_csv).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def open_review(root,labels_csv):
    path=Path(labels_csv);rows=read_rows(path)
    if not rows:messagebox.showerror('No images','No images were prepared for labeling.');return
    win=tk.Toplevel(root);win.title('Verify evidence — human labeling');win.geometry('1080x785')
    top=ttk.Frame(win,padding=12);top.pack(fill='x');status=tk.StringVar();ttk.Label(top,text='Evidence Verification',font=('Segoe UI',16,'bold')).pack(anchor='w');ttk.Label(top,text='Review each image. Never infer a load solely from its filename. Saved labels are evaluation ground truth, not automatic COR approval.',wraplength=1000).pack(anchor='w')
    ttk.Label(top,textvariable=status).pack(anchor='w',pady=4)
    panel=ttk.Frame(win,padding=10);panel.pack(fill='both',expand=True)
    preview=ttk.Label(panel,anchor='center');preview.pack(fill='both',expand=True)
    desc=tk.StringVar();ttk.Label(panel,textvariable=desc,wraplength=980).pack(anchor='w')
    controls=ttk.Frame(panel);controls.pack(fill='x',pady=8)
    cat=tk.StringVar(); load=tk.StringVar();note=tk.StringVar();reviewer=tk.StringVar()
    ttk.Label(controls,text='Photo type').grid(row=0,column=0,sticky='w'); ttk.Combobox(controls,values=CATEGORIES,textvariable=cat,state='readonly',width=30).grid(row=1,column=0,padx=4)
    ttk.Label(controls,text='Load # (only if evident)').grid(row=0,column=1,sticky='w');ttk.Entry(controls,textvariable=load,width=13).grid(row=1,column=1,padx=4)
    ttk.Label(controls,text='Notes').grid(row=0,column=2,sticky='w');ttk.Entry(controls,textvariable=note,width=40).grid(row=1,column=2,padx=4)
    ttk.Label(controls,text='Reviewer').grid(row=0,column=3,sticky='w');ttk.Entry(controls,textvariable=reviewer,width=18).grid(row=1,column=3,padx=4)
    suggestions={}
    predicted=path.parent/'suggestions'/'predictions.csv'
    if predicted.exists():
        try:
            suggestions={r['id']:r for r in read_rows(predicted)}
        except Exception:pass
    suggestion_line=tk.StringVar()
    ttk.Label(panel,textvariable=suggestion_line,wraplength=980,foreground='#91610d').pack(anchor='w',pady=(0,5))
    index=[0];cache=[None]
    def show():
        row=rows[index[0]]
        try:
            with Image.open(path.parent/row['thumbnail']) as img:
                img=img.copy();img.thumbnail((1000,510));cache[0]=ImageTk.PhotoImage(img)
            preview.config(image=cache[0],text='')
        except Exception as e:preview.config(image='',text=str(e))
        cat.set(row['category']);load.set(row['load_number']);note.set(row['notes']);reviewer.set(row.get('reviewer',''))
        desc.set(f"{row['work_order']} · Image {index[0]+1}/{len(rows)} · {row['original_name']}")
        suggestion=suggestions.get(row['id'])
        if suggestion:
            suggestion_line.set('Unverified suggestion: '+suggestion['predicted_category']+' | '+suggestion.get('reason','')+' | Visually close images: '+suggestion.get('nearest_images',''))
        else:suggestion_line.set('No prediction available. Classify this image based on what it actually shows.')
        total=sum(r['category']!='Unreviewed' for r in rows)
        status.set(f'{total} / {len(rows)} labeled · {len(rows)-total} left')
    def store():
        from datetime import datetime,timezone
        row=rows[index[0]];row['category']=cat.get();row['load_number']=load.get().strip();row['notes']=note.get().strip();row['reviewer']=reviewer.get().strip();row['reviewed_at']=datetime.now(timezone.utc).isoformat() if row['category']!='Unreviewed' else ''
        save_rows(path,rows)
    def move(change):store();index[0]=max(0,min(len(rows)-1,index[0]+change));show()
    foot=ttk.Frame(panel);foot.pack(fill='x')
    ttk.Button(foot,text='← Previous',command=lambda:move(-1)).pack(side='left',padx=4)
    ttk.Button(foot,text='Save & Next →',command=lambda:move(1)).pack(side='left',padx=4)
    ttk.Button(foot,text='Save',command=store).pack(side='left',padx=4)
    ttk.Button(foot,text='Next Unreviewed',command=lambda: (store(),index.__setitem__(0,next((i for i,r in enumerate(rows) if r['category']=='Unreviewed'),index[0])),show())).pack(side='left',padx=4)
    win.protocol('WM_DELETE_WINDOW',lambda:(store(),win.destroy()))
    show()
