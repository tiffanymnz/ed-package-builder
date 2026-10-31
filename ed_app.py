"""ED Package Builder v3 — offline Windows-first case workspace.
Human-assigned images; no claimed AI automation. Launch: python ed_app.py
"""
import json,hashlib,shutil,zipfile,os,subprocess,sys,tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from ed_builder import build,volume,ALL
from evidence_engine import export as triage_export
from visual_gallery import gallery as open_visual_gallery
from visual_intake import export as visual_intake_export
from ground_truth_review import sample_archives, open_review
from image_suggestions import candidates as suggest_candidates
from evidence_timeline import make_report as make_timeline
from evidence_matcher import rank_similar
from text_evidence import analyze as ocr_analyze, available as ocr_available
from evidence_audit import write_report, collect as audit_evidence
from vision_adapter import analyze_local

BASE=Path.home()/ 'ED_Package_Builder_Cases'
IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
ACCEPT=IMAGE_EXT|{'.pdf','.docx','.txt'}
PHOTO_SLOTS=[x for x in ALL if x!='calculator']+['disposal_photo','first_10_proof','measurement_extra_1','measurement_extra_2','measurement_extra_3']
PHASES=['before_photos','during_photos','after_photos','financial_pdfs']

def safe(s):return ''.join(x if x.isalnum() or x in '-_' else '_' for x in s)[:80]
def as_number(value,default=0):
    try:return float(value)
    except:return default

def default_load(n):
    return {'name':f'Load {n}','length_ft':'','width_ft':'','side_height_ft':'','overage_height_ft':0,'overage_cyd':0,'overage_note':'','measured_load_cyd':None,'photos':{},'extra_measurement_photos':[],'disposal_photo':'','evidence_first_10_cyd':''}

def make_case(case,address,vendor,loads,rate):
    return dict(case_number=case,address=address,vendor=vendor,rate_per_cyd=rate,deduct_first_10_cyd=True,
      loads=[default_load(i) for i in range(1,loads+1)],financial_pdfs=[],before_photos=[],during_photos=[],after_photos=[],
      invoice_quantity_cyd='',invoice_amount_usd='',invoice_deduction_usd='',
      invoice_quantity_basis='unknown',invoice_deduction_status='unknown',first_10_prior_work='unknown',verified_first_10_amount='',financial_confirmation_hash='',financial_confirmation_note='',
      photo_assignments={},imported_files=[],review_confirmed=False)

class App:
 def __init__(self,root):
    self.root=root;root.title('ED Package Builder — Portable Pilot (v16)');root.geometry('1160x790')
    self.case=None;self.case_dir=None;self.selected_photo=None;self.photos=[];self.thumb_cache={};self.vars={}
    self.bar=ttk.Frame(root,padding=12);self.bar.pack(fill='x')
    ttk.Label(self.bar,text='ED PACKAGE BUILDER',font=('Segoe UI',16,'bold')).pack(side='left')
    for label,fn in [('New Case',self.new_case),('Open Case',self.open_case),('Save',self.save),('Import Folder',self.import_files),('Import ZIPs',self.import_zips),('Analyze Files',self.analyze_files),('Visual Gallery',self.visual_gallery),('Visual Triage',self.visual_triage),('Timeline Review',self.timeline_review),('Similar Photos',self.similar_photos),('Read Photo Text',self.read_photo_text),('Local AI Review',self.local_ai_review),('Audit Evidence',self.audit_evidence),('Verify Samples',self.verify_samples),('Suggest Sample Types',self.suggest_sample_types),('Generate Draft',self.generate),('Transmittal PDF',self.transmittal)]:
       ttk.Button(self.bar,text=label,command=fn).pack(side='right',padx=3)
    self.status=tk.StringVar(value='Create or open a case. Evidence matching remains manual; validation is automatic.')
    ttk.Label(root,textvariable=self.status,foreground='#57616b').pack(fill='x',padx=14)
    self.guide=ttk.Frame(root,padding=(12,5));self.guide.pack(fill='x')
    self.guide_title=ttk.Label(self.guide,text='Start with a case, add all vendor files, review issues, then generate a draft.',font=('Segoe UI',11,'bold'));self.guide_title.pack(anchor='w')
    nav=ttk.Frame(self.guide);nav.pack(fill='x',pady=8)
    self.nav=nav
    self.tabs=ttk.Notebook(root);self.tabs.pack(expand=True,fill='both',padx=12,pady=8)
    self.case_tab=ttk.Frame(self.tabs,padding=10);self.evidence_tab=ttk.Frame(self.tabs,padding=10);self.finance_tab=ttk.Frame(self.tabs,padding=10);self.check_tab=ttk.Frame(self.tabs,padding=10)
    for tab,title in [(self.case_tab,'1 · Case & Loads'),(self.evidence_tab,'2 · Import & Photos'),(self.finance_tab,'3 · Invoice'),(self.check_tab,'4 · Review Issues')]:self.tabs.add(tab,text=title)
    self.draw_case();self.draw_evidence();self.draw_finance();self.draw_checks()
    for i,(label,desc) in enumerate([('1  Case','Details & load measurements'),('2  Photos','Import and assign evidence'),('3  Invoice','Verify first 10 CYD deduction'),('4  Issues','Validate before export')]):
       b=ttk.Button(nav,text=label,command=lambda j=i:self.tabs.select(j));b.pack(side='left',padx=(0,10))
    ttk.Button(nav,text='How it works',command=self.help).pack(side='right')
    self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.update_guide())

 def update_guide(self):
    notes=['Step 1: Confirm the case and enter vendor-measured dimensions for each load.','Step 2: Import all source files, then assign original images to the matching load or property section.','Step 3: Confirm case-specific first-10-CYD amount, invoice quantity, and existing deduction.','Step 4: Resolve missing evidence and invoice conflicts. Generate only a DRAFT until final human review.']
    try:self.guide_title.configure(text=notes[self.tabs.index(self.tabs.select())])
    except Exception:pass
 def help(self):
    messagebox.showinfo('ED Package Builder — How to use',
      '1. NEW CASE: enter case number, vendor and estimated load count.\n\n'
      '2. IMPORT: select a folder with ReamsView downloads, saved Outlook files or ZIPs. You can import again after corrections.\n\n'
      '3. PHOTOS: choose the load and required slot, preview the file, then click Assign. This version DOES NOT identify unlabeled photos automatically.\n\n'
      '4. MEASUREMENTS: enter documented length, width and height in feet, plus supported overage.\n\n'
      '5. INVOICE: manually confirm applicable deduction amount and whether invoice CYD includes the first 10.\n\n'
      '6. REVIEW: inspect all exceptions. Draft exports are not COR approvals. Save is automatic after assignments; use Save for field edits.')

 def require(self):
    if self.case is None:messagebox.showwarning('Open a case','Create or open a case first.');return False
    return True
 def new_case(self):
    win=tk.Toplevel(self.root);win.title('New case');win.geometry('425x300');win.transient(self.root);win.grab_set()
    fields=[('Case number','093-EXAMPLE'),('Property address',''),('Vendor',''),('Number of loads','3'),('ED rate per CYD','35')]
    entries={}
    for i,(lab,default) in enumerate(fields):
       ttk.Label(win,text=lab).grid(row=i,column=0,padx=10,pady=8,sticky='w');e=ttk.Entry(win,width=27);e.insert(0,default);e.grid(row=i,column=1,pady=8);entries[lab]=e
    def create():
       try:
          n=int(entries['Number of loads'].get());assert 1<=n<=150
          case=entries['Case number'].get().strip();assert case
          d=BASE/safe(case);d.mkdir(parents=True,exist_ok=True)
          if (d/'case.json').exists():raise ValueError('Case already exists; use Open Case')
          self.case=make_case(case,entries['Property address'].get(),entries['Vendor'].get(),n,as_number(entries['ED rate per CYD'].get(),35));self.case_dir=d;self.save();self.refresh();win.destroy()
       except Exception as e:messagebox.showerror('Case error',str(e))
    ttk.Button(win,text='Create Case',command=create).grid(row=6,column=1,sticky='e',pady=12)
 def open_case(self):
    path=filedialog.askopenfilename(title='Open case.json',filetypes=[('ED case','case.json'),('JSON','*.json')]);
    if not path:return
    try:
       self.case=json.loads(Path(path).read_text(encoding='utf-8'));self.case_dir=Path(path).parent;self.refresh()
    except Exception as e:messagebox.showerror('Open error',str(e))
 def save(self):
    if self.case is None:return
    self.sync_case();self.case_dir.mkdir(parents=True,exist_ok=True)
    (self.case_dir/'case.json').write_text(json.dumps(self.case,indent=2),encoding='utf-8');self.status.set('Saved: '+str(self.case_dir/'case.json'))
 def sync_case(self):
    if self.case is None:return
    for key,var in self.vars.items():
       value=var.get()
       if key.startswith('L:'):
          _,index,k=key.split(':');self.case['loads'][int(index)][k]=value
       else:self.case[key]=value
 def refresh(self):
    self.vars={};self.photos=[];self.thumb_cache={};self.draw_case();self.draw_evidence();self.draw_finance();self.draw_checks();self.update_guide()
    self.status.set(f"Case {self.case['case_number']} — {len(self.case['loads'])} loads. Originals retained in {self.case_dir}")
 def draw_case(self):
    for w in self.case_tab.winfo_children():w.destroy()
    if not self.case:return
    header=ttk.Frame(self.case_tab);header.pack(fill='x')
    for label,k in [('Case','case_number'),('Address','address'),('Vendor','vendor'),('Rate/CYD','rate_per_cyd')]:
       ttk.Label(header,text=label).pack(side='left',padx=(9,3));v=tk.StringVar(value=str(self.case.get(k,'')));self.vars[k]=v;ttk.Entry(header,textvariable=v,width=15 if k!='address' else 32).pack(side='left',padx=4)
    ttk.Button(self.case_tab,text='+ Add Load',command=self.add_load).pack(anchor='e',pady=8)
    canvas=tk.Canvas(self.case_tab);scroll=ttk.Scrollbar(self.case_tab,orient='vertical',command=canvas.yview);interior=ttk.Frame(canvas)
    interior.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0,0),window=interior,anchor='nw');canvas.configure(yscrollcommand=scroll.set);canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
    for i,load in enumerate(self.case['loads']):
       f=ttk.LabelFrame(interior,text=f'Load {i+1} — vendor measurements in feet',padding=9);f.pack(fill='x',pady=4,padx=4)
       for j,(label,key) in enumerate([('Length','length_ft'),('Width','width_ft'),('Wall height','side_height_ft'),('Uniform overage height','overage_height_ft'),('Separate overage CYD','overage_cyd'),('Overage evidence / note','overage_note')]):
          ttk.Label(f,text=label).grid(row=j//3*2,column=(j%3)*2,sticky='w',padx=5)
          v=tk.StringVar(value=str(load.get(key,'') if load.get(key) is not None else ''));self.vars[f'L:{i}:{key}']=v
          ttk.Entry(f,textvariable=v,width=21 if key=='overage_note' else 12).grid(row=j//3*2+1,column=(j%3)*2,sticky='w',padx=5,pady=3)
 def add_load(self):
    if not self.require():return
    self.sync_case();self.case['loads'].append(default_load(len(self.case['loads'])+1));self.refresh()
 def import_files(self):
    if not self.require():return
    src=filedialog.askdirectory(title='Choose downloaded evidence folder')
    if src:self._import_paths([p for p in Path(src).rglob('*') if p.is_file() and p.suffix.lower() in ACCEPT|{'.zip'}])
 def import_zips(self):
    if not self.require():return
    paths=filedialog.askopenfilenames(title='Select vendor ZIP exports (you can select several)',filetypes=[('ZIP files','*.zip')])
    if paths:self._import_paths([Path(p) for p in paths])
 def _import_paths(self,files):
    self.save();dest=self.case_dir/'originals';dest.mkdir(exist_ok=True)
    existing={e['sha256'] for e in self.case.get('imported_files',[]) if e.get('sha256')}
    added=duplicate=0;issues=[];MAX=150*1024*1024
    for p in files:
       try:
          if p.suffix.lower()=='.zip':
             with zipfile.ZipFile(p) as z:
                for member in z.infolist():
                   if member.is_dir() or Path(member.filename).suffix.lower() not in ACCEPT:continue
                   if member.file_size>MAX:issues.append(f'{p.name}::{member.filename}: too large');continue
                   try:
                      with z.open(member) as stream:
                         a,d=self._store_stream(stream,f'{p.name}::{member.filename}',Path(member.filename).name,dest,existing,MAX)
                      added+=a;duplicate+=d
                   except Exception as e:issues.append(f'{p.name}::{member.filename}: {e}')
          elif p.suffix.lower() in ACCEPT:
             if p.stat().st_size>MAX:issues.append(f'{p.name}: too large');continue
             with p.open('rb') as stream:
                a,d=self._store_stream(stream,str(p),p.name,dest,existing,MAX)
             added+=a;duplicate+=d
       except Exception as e:issues.append(f'{p.name}: {e}')
    self.save();self.refresh()
    if issues:(self.case_dir/'import_warnings.txt').write_text('\n'.join(issues),encoding='utf-8')
    messagebox.showinfo('Import complete',f'Imported: {added}\nExact duplicates: {duplicate}\nWarnings: {len(issues)}\nFiles saved under: {dest}\n\nImport ZIPs directly next time; no need to extract them first.')
 def _store_stream(self,stream,source,name,dest,existing,limit):
    digest=hashlib.sha256();size=0
    fd,tmp=tempfile.mkstemp(prefix='.import-',dir=str(dest))
    try:
       with os.fdopen(fd,'wb') as out:
          while True:
             chunk=stream.read(1024*1024)
             if not chunk:break
             size+=len(chunk)
             if size>limit:raise ValueError('File exceeds safe import size')
             digest.update(chunk);out.write(chunk)
       sig=digest.hexdigest()
       if sig in existing:return 0,1
       existing.add(sig)
       path=dest/(sig[:12]+'_'+safe(Path(name).stem)+Path(name).suffix.lower())
       os.replace(tmp,path);tmp=None
       self.case.setdefault('imported_files',[]).append({'source':source,'path':str(path),'sha256':sig,'name':name})
       return 1,0
    finally:
       if tmp and os.path.exists(tmp):os.unlink(tmp)
 def visual_gallery(self):
    if not self.require():return
    def select_photo(record):
       self.tabs.select(self.evidence_tab)
       for i,item in enumerate(self.photos):
          if item['path']==record['path']:
             self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
    open_visual_gallery(self.root,self.case.get('imported_files',[]),select_photo)

 def read_photo_text(self):
    if not self.require():return
    if not ocr_available():
       messagebox.showwarning('Text recognition unavailable','Optional Tesseract OCR is not available on this computer. No load or receipt is automatically identified.\n\nThe rest of the package builder still works. Ask IT before installing OCR software.')
       return
    self.save()
    try:
       rows=ocr_analyze(self.case.get('imported_files',[]),self.case_dir/'analysis')
       win=tk.Toplevel(self.root);win.title('Photo Text — Unverified OCR Suggestions');win.geometry('1100x620')
       ttk.Label(win,text=f'Possible load signs and receipts: {len(rows)} scanned photos',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=12,pady=7)
       ttk.Label(win,text='OCR errors are common. Verify the photo; no load slots, numbers, or financial values are automatically confirmed.').pack(anchor='w',padx=12)
       frm=ttk.Frame(win,padding=10);frm.pack(fill='both',expand=True)
       cols=('file','load_candidate','stage_candidate','receipt_terms','case_candidate','ocr_excerpt')
       tree=ttk.Treeview(frm,columns=cols,show='headings')
       for col,width in [('file',190),('load_candidate',65),('stage_candidate',70),('receipt_terms',160),('case_candidate',100),('ocr_excerpt',400)]:
          tree.heading(col,text=col.replace('_',' ').title());tree.column(col,width=width)
       for i,r in enumerate(rows):
          if r['load_candidate'] or r['stage_candidate'] or r['receipt_terms'] or r['case_candidate']:
             tree.insert('','end',iid=str(i),values=tuple(r[c] for c in cols))
       tree.pack(side='left',fill='both',expand=True)
       sb=ttk.Scrollbar(frm,orient='vertical',command=tree.yview);sb.pack(side='right',fill='y');tree.configure(yscrollcommand=sb.set)
       def open_photo():
          if not tree.selection():return
          path=rows[int(tree.selection()[0])]['path']
          self.tabs.select(self.evidence_tab)
          for i,photo in enumerate(self.photos):
             if photo['path']==path:
                self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
          win.destroy()
       ttk.Button(win,text='Inspect selected original photo',command=open_photo).pack(pady=8)
       tree.bind('<Double-1>',lambda e:open_photo())
       self.status.set('OCR review created. No files automatically assigned; all text findings need visual confirmation.')
    except Exception as e:messagebox.showerror('Photo text analysis error',str(e))

 def visual_triage(self):
    if not self.require():return
    self.save()
    try:
       rows,counts=visual_intake_export(self.case,self.case_dir/'analysis')
       win=tk.Toplevel(self.root);win.title('Visual Review — Unverified suggestions');win.geometry('1080x640')
       ttk.Label(win,text=f'Image-content review: {len(rows):,} images',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=8)
       ttk.Label(win,text='Visual candidates are NOT verified receipts, measurements or loads. Open an image to assign it; evidence is never automatically accepted.',wraplength=1020).pack(anchor='w',padx=12)
       ttk.Label(win,text='Saved Visual_Review_Candidates.csv and .json in your case analysis folder.').pack(anchor='w',padx=12)
       frm=ttk.Frame(win,padding=10);frm.pack(fill='both',expand=True)
       tree=ttk.Treeview(frm,columns=('name','candidate','nearby'),show='headings')
       for col,width in [('name',260),('candidate',300),('nearby',400)]:tree.heading(col,text=col.title());tree.column(col,width=width)
       for i,r in enumerate(rows):tree.insert('', 'end',iid=str(i),values=(r['file'],r['candidate'],', '.join(r['nearby_similar_files'])[:75]))
       tree.pack(side='left',fill='both',expand=True)
       sb=ttk.Scrollbar(frm,orient='vertical',command=tree.yview);sb.pack(side='right',fill='y');tree.configure(yscrollcommand=sb.set)
       def select():
          if not tree.selection():return
          item=rows[int(tree.selection()[0])]
          self.tabs.select(self.evidence_tab)
          for i,photo in enumerate(self.photos):
             if photo['path']==item['path']:
                self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
          win.destroy()
       ttk.Button(win,text='Open selected photo for review / assignment',command=select).pack(pady=9)
       tree.bind('<Double-1>',lambda e:select())
       self.status.set(f'Visual triage complete: {len(rows):,} unverified image suggestions; no automatic assignments made.')
    except Exception as e:messagebox.showerror('Visual triage error',str(e))

 def timeline_review(self):
    if not self.require():return
    self.save()
    try:
       rows,summary=make_timeline(self.case.get('imported_files',[]),self.case_dir/'analysis')
       win=tk.Toplevel(self.root);win.title('Evidence Timeline — Not verified loads');win.geometry('1100x640')
       ttk.Label(win,text=f"{summary['photos_analyzed']:,} photos analyzed — timeline suggestions only",font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=8)
       ttk.Label(win,text='Clusters are based on genuine EXIF capture dates only. No date? No inferred sequence. Neither similar photos nor time clusters prove a load.',wraplength=1040).pack(anchor='w',padx=12)
       frm=ttk.Frame(win,padding=10);frm.pack(fill='both',expand=True)
       tree=ttk.Treeview(frm,columns=('file','date','cluster','repeat'),show='headings')
       for col,width in [('file',300),('date',160),('cluster',250),('repeat',250)]:tree.heading(col,text=col.title());tree.column(col,width=width)
       for i,item in enumerate(rows):tree.insert('','end',iid=str(i),values=(item['file'],item['exif_datetime'] or 'Not available',item['sequence_group'],item['possible_repeat_of'][:40]))
       tree.pack(side='left',fill='both',expand=True)
       sb=ttk.Scrollbar(frm,orient='vertical',command=tree.yview);sb.pack(side='right',fill='y');tree.configure(yscrollcommand=sb.set)
       def open_photo():
          if not tree.selection():return
          path=rows[int(tree.selection()[0])]['path']
          self.tabs.select(self.evidence_tab)
          for i,photo in enumerate(self.photos):
             if photo['path']==path:
                self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
          win.destroy()
       ttk.Button(win,text='Review selected original photo',command=open_photo).pack(pady=8)
       tree.bind('<Double-1>',lambda e:open_photo())
       self.status.set('Timeline saved in case analysis folder. No load assignments changed.')
    except Exception as e:messagebox.showerror('Timeline error',str(e))

 def similar_photos(self):
    if not self.require():return
    if not self.selected_photo or Path(self.selected_photo).suffix.lower() not in IMAGE_EXT:
       messagebox.showinfo('Select a photograph','Open the Import & Photos section and select a photograph first.');return
    try:
       matches=rank_similar(self.selected_photo,self.case.get('imported_files',[]),limit=20)
       win=tk.Toplevel(self.root);win.title('Similar photos — suggestions only');win.geometry('880x590')
       ttk.Label(win,text='Potential visual matches (NOT verified same load)',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=12,pady=8)
       ttk.Label(win,text='The strongest appearance matches are listed first. Similar-looking trailer photos can belong to different loads. Confirm visually before assigning.',wraplength=800).pack(anchor='w',padx=12)
       tree=ttk.Treeview(win,columns=('photo','score','repeat'),show='headings')
       for k,w in [('photo',580),('score',110),('repeat',120)]:tree.heading(k,text=k.title());tree.column(k,width=w)
       for i,r in enumerate(matches):tree.insert('','end',iid=str(i),values=(r['name'],f"{r['score']:.3f} (ranking only)",'Possible repeat' if r['possible_repeat'] else ''))
       tree.pack(fill='both',expand=True,padx=12,pady=8)
       def choose():
          if not tree.selection():return
          p=matches[int(tree.selection()[0])]['path']
          self.tabs.select(self.evidence_tab)
          for i,photo in enumerate(self.photos):
             if photo['path']==p:
                self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
          win.destroy()
       ttk.Button(win,text='Review selected photo (does not assign)',command=choose).pack(pady=8)
       tree.bind('<Double-1>',lambda e:choose())
    except Exception as e:messagebox.showerror('Matching error',str(e))

 def verify_samples(self):
    if not self.require():return
    folder=self.case_dir/'verified_test_set'
    labels=folder/'labels.csv'
    try:
       if not labels.exists():
          zips=filedialog.askopenfilenames(title='Select vendor work-order ZIPs for evaluation (separate properties)',filetypes=[('ZIP files','*.zip')])
          if not zips:return
          rows=sample_archives(zips,folder,per_archive=24)
          if not rows:messagebox.showwarning('No photos','No suitable image samples were found');return
       open_review(self.root,labels)
    except Exception as e:messagebox.showerror('Verification error',str(e))

 def suggest_sample_types(self):
    if not self.require():return
    labels=self.case_dir/'verified_test_set'/'labels.csv'
    if not labels.exists():
       selected=filedialog.askopenfilename(title='Select existing verified-sample labels.csv',filetypes=[('CSV','*.csv')])
       if not selected:return
       labels=Path(selected)
    try:
       out=labels.parent/'suggestions'; report=suggest_candidates(labels,out)
       messagebox.showinfo('Unverified image suggestions',f"Prepared {report['total']} photo suggestions.\n\nCategory breakdown: {report['predictions']}\n\nPredictions are NOT verified and will not be assigned to COR slots.\nSaved to: {out}\n\nUse Verify Samples to establish actual labels.")
    except Exception as e:messagebox.showerror('Suggestion error',str(e))

 def local_ai_review(self):
    if not self.require():return
    # An explicit per-run choice: no images are transmitted automatically.
    from tkinter import simpledialog
    files=[Path(e['path']) for e in self.case.get('imported_files',[]) if Path(e.get('path','')).suffix.lower() in IMAGE_EXT and Path(e.get('path','')).is_file()]
    if not files:messagebox.showwarning('No photos','Import an evidence folder or ZIP first.');return
    if not messagebox.askyesno('Optional LOCAL vision review',
       'This optional feature uses an Ollama vision model running on your own computer at 127.0.0.1:11434.\n\n'
       'It is NOT included with the application. Install and approve a local vision model separately.\n\n'
       'Results are suggestions only, never COR-ready assignments. No remote AI endpoint is used.\n\nRun on a small set now?'):
       return
    model=simpledialog.askstring('Local vision model','Ollama model name installed locally:',initialvalue='llava',parent=self.root)
    if not model:return
    count=simpledialog.askinteger('Batch limit','Analyze up to how many photos this run? Start with 5.',initialvalue=5,minvalue=1,maxvalue=50,parent=self.root)
    if count is None:return
    out_dir=self.case_dir/'local_vision_review';out_dir.mkdir(exist_ok=True)
    report=out_dir/'suggestions.json';rows=[]
    if report.exists():
       try:rows=json.loads(report.read_text(encoding='utf-8'))
       except Exception:rows=[]
    done={r.get('file') for r in rows}
    failures=[]
    for f in files:
       if len([r for r in rows if r.get('run_id')=='current'])>=count:break
       if str(f) in done:continue
       try:
          pred=analyze_local(f,model=model)
          rows.append({'file':str(f),'prediction':pred,'model':model,'run_id':'current'})
       except Exception as exc:
          failures.append(str(exc));break
    for row in rows:row.pop('run_id',None)
    report.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    if failures:messagebox.showwarning('Local vision unavailable',
       'No cloud fallback was attempted. Check whether Ollama and the specified vision model are installed and running.\n\n'+failures[0][:300])
    win=tk.Toplevel(self.root);win.title('LOCAL AI suggestions — UNVERIFIED');win.geometry('1030x520')
    ttk.Label(win,text='Unverified suggestions only — do not auto-assign to COR package',font=('Segoe UI',11,'bold')).pack(anchor='w',padx=12,pady=8)
    tree=ttk.Treeview(win,columns=('file','type','stage','load','why'),show='headings')
    for col,w in [('file',300),('type',150),('stage',75),('load',75),('why',390)]:
       tree.heading(col,text=col.title());tree.column(col,width=w)
    for i,r in enumerate(rows):
       x=r['prediction'];tree.insert('', 'end',iid=str(i),values=(Path(r['file']).name,x['category'],x['stage'],x['load_number'] or '—',x['reason']))
    tree.pack(fill='both',expand=True,padx=12,pady=8)
    def inspect():
       selected=tree.selection()
       if not selected:return
       path=Path(rows[int(selected[0])]['file'])
       try:os.startfile(str(path)) if sys.platform=='win32' else subprocess.Popen(['xdg-open',str(path)])
       except Exception as exc:messagebox.showerror('Photo preview',str(exc))
    ttk.Button(win,text='Open original photo',command=inspect).pack(pady=8)
    self.status.set('Local AI suggestions saved for human review: '+str(report))

 def analyze_files(self):
    if not self.require():return
    self.save()
    try:
       rows,summary=triage_export(self.case,self.case_dir/'analysis')
       self.case['analysis_summary']=summary
       self.save()
       # Display unassigned and flagged evidence without treating guesses as verified.
       win=tk.Toplevel(self.root);win.title('Evidence Triage — Suggestions only');win.geometry('1050x580')
       ttk.Label(win,text=f"Analyzed {summary['files_analyzed']} files · {summary['partially_labeled']} with clues · {summary['unclassified']} unclassified · {summary['possible_near_duplicates']} possible image matches",font=('Segoe UI',11,'bold')).pack(padx=12,pady=10,anchor='w')
       ttk.Label(win,text='These are unverified filename/metadata suggestions, NOT AI visual classification. Click a row to inspect its source. Reports saved in the case analysis folder.',wraplength=950).pack(anchor='w',padx=12)
       frame=ttk.Frame(win);frame.pack(fill='both',expand=True,padx=12,pady=10)
       tree=ttk.Treeview(frame,columns=('file','load','type','confidence','duplicates'),show='headings')
       for key,width in [('file',350),('load',70),('type',210),('confidence',100),('duplicates',100)]:tree.heading(key,text=key.title());tree.column(key,width=width)
       for i,row in enumerate(rows):tree.insert('', 'end',iid=str(i),values=(row['file'],row['suggested_load'] or '—',', '.join(row['suggested_slots'] or row['document_hints']) or 'unclassified',row['confidence'],'Review' if row['possible_visual_duplicate'] else ''))
       tree.pack(side='left',fill='both',expand=True)
       scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set)
       def review():
          selection=tree.selection()
          if not selection:return
          row=rows[int(selection[0])]
          # Navigate to imported item for manual verification and assignment.
          self.tabs.select(self.evidence_tab)
          for i,record in enumerate(self.photos):
             if record['path']==row['path']:
                self.filelist.selection_clear(0,'end');self.filelist.selection_set(i);self.filelist.see(i);self.preview();break
          win.destroy()
       ttk.Button(win,text='Review selected source photo',command=review).pack(padx=12,pady=8)
    except Exception as e:messagebox.showerror('Evidence analysis error',str(e))

 def draw_evidence(self):
    for w in self.evidence_tab.winfo_children():w.destroy()
    if not self.case:return
    top=ttk.Frame(self.evidence_tab);top.pack(fill='x',pady=5)
    ttk.Label(top,text='Choose load').pack(side='left');self.e_load=tk.StringVar(value='1')
    ttk.Combobox(top,textvariable=self.e_load,values=[str(i) for i in range(1,len(self.case['loads'])+1)],width=8,state='readonly').pack(side='left',padx=6)
    ttk.Label(top,text='Slot').pack(side='left',padx=(16,0));self.slot=tk.StringVar(value='empty')
    ttk.Combobox(top,textvariable=self.slot,values=PHOTO_SLOTS+PHASES,width=25,state='readonly').pack(side='left',padx=6)
    ttk.Button(top,text='Assign selected image',command=self.assign).pack(side='left',padx=8)
    ttk.Button(top,text='Clear slot',command=self.clear_slot).pack(side='left')
    body=ttk.Frame(self.evidence_tab);body.pack(fill='both',expand=True)
    left=ttk.LabelFrame(body,text='Imported files — select an image',padding=4);left.pack(side='left',fill='both',expand=True)
    self.filelist=tk.Listbox(left,width=55,exportselection=False);self.filelist.pack(fill='both',expand=True,side='left');scroll=ttk.Scrollbar(left,orient='vertical',command=self.filelist.yview);scroll.pack(side='left',fill='y');self.filelist.configure(yscrollcommand=scroll.set)
    self.photos=self.case.get('imported_files',[])
    for entry in self.photos:self.filelist.insert('end',entry['name']+'   ['+Path(entry['path']).suffix.lower()+']')
    self.filelist.bind('<<ListboxSelect>>',self.preview)
    right=ttk.LabelFrame(body,text='Image preview and assignment status',padding=8);right.pack(side='left',fill='both',expand=True,padx=9)
    self.preview_label=ttk.Label(right,text='Select image');self.preview_label.pack(pady=6)
    self.selected_label=ttk.Label(right,text='No photo selected',wraplength=420);self.selected_label.pack(pady=6)
    self.assigned=tk.Text(right,width=49,height=17);self.assigned.pack(fill='both',expand=True)
    ttk.Button(right,text='Refresh evidence summary',command=self.refresh_assignments).pack(pady=5)
    self.refresh_assignments()
 def preview(self,event=None):
    selections=self.filelist.curselection()
    if not selections:return
    item=self.photos[selections[0]];self.selected_photo=item['path'];self.selected_label.configure(text=item['name']+'\n'+item['source'])
    try:
       p=Path(item['path'])
       if p.suffix.lower()=='.pdf':
          import fitz
          d=fitz.open(str(p));pix=d[0].get_pixmap(matrix=fitz.Matrix(1.0,1.0));im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);d.close()
       else:im=Image.open(p).convert('RGB')
       im.thumbnail((430,320));self.current_image=ImageTk.PhotoImage(im);self.preview_label.configure(image=self.current_image,text='')
    except Exception:self.preview_label.configure(image='',text='Preview unavailable (not an image)')
 def assign(self):
    if not self.require() or not self.selected_photo:return
    slot=self.slot.get();p=self.selected_photo
    if slot in PHASES:
       if slot=='financial_pdfs' and Path(p).suffix.lower()!='.pdf':messagebox.showwarning('PDF required','Financial attachments must be PDFs');return
       if p not in self.case[slot]:self.case[slot].append(p)
    else:
       load=self.case['loads'][int(self.e_load.get())-1]
       if slot=='disposal_photo':load['disposal_photo']=p
       elif slot=='first_10_proof':load['evidence_first_10_cyd']=p
       elif slot.startswith('measurement_extra_'):
          if p not in load['extra_measurement_photos']:load['extra_measurement_photos'].append(p)
       else:load['photos'][slot]=p
    self.save();self.refresh_assignments()
 def clear_slot(self):
    if not self.require():return
    slot=self.slot.get()
    if slot in PHASES:self.case[slot]=[]
    else:
       l=self.case['loads'][int(self.e_load.get())-1]
       if slot=='disposal_photo':l['disposal_photo']=''
       elif slot=='first_10_proof':l['evidence_first_10_cyd']=''
       elif slot.startswith('measurement_extra_'):l['extra_measurement_photos']=[]
       else:l['photos'].pop(slot,None)
    self.save();self.refresh_assignments()
 def refresh_assignments(self):
    if not hasattr(self,'assigned'):return
    self.assigned.delete('1.0','end')
    for i,l in enumerate(self.case['loads'],1):
       self.assigned.insert('end',f'LOAD {i}\n')
       for slot in PHOTO_SLOTS[:10]:self.assigned.insert('end',f'  {slot}: {"OK" if l.get("photos",{}).get(slot) else "MISSING"}\n')
       self.assigned.insert('end',f'  Disposal photo: {bool(l.get("disposal_photo"))}; extras: {len(l.get("extra_measurement_photos",[]))}\n\n')
    for slot in PHASES:self.assigned.insert('end',f'{slot}: {len(self.case.get(slot,[]))} files\n')
 def draw_finance(self):
    for w in self.finance_tab.winfo_children():w.destroy()
    if not self.case:return
    ttk.Label(self.finance_tab,text='Independent checks: invoiced CYD + manually verified first-10-CYD dollar amount',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=10)
    keys=[('Vendor invoice CYD quantity','invoice_quantity_cyd'),('Vendor invoice net amount ($)','invoice_amount_usd'),('Explicit deduction shown on invoice ($)','invoice_deduction_usd'),('Verified applicable first-10-CYD amount ($)','verified_first_10_amount'),('Reason / work-order reference','financial_confirmation_note')]
    for label,key in keys:
       row=ttk.Frame(self.finance_tab);row.pack(fill='x',pady=6)
       ttk.Label(row,text=label,width=43).pack(side='left');v=tk.StringVar(value=str(self.case.get(key,'')));self.vars[key]=v;ttk.Entry(row,textvariable=v,width=20).pack(side='left')
    selections=[('Invoice quantity includes the first 10 CYD?','invoice_quantity_basis',[('Unknown','unknown'),('Full measured quantity included','includes'),('First 10 excluded from quantity','excludes')]),
      ('First-10 deduction already reflected on invoice?','invoice_deduction_status',[('Unknown','unknown'),('Yes, separately deducted','yes'),('No','no'),('Alternate billing presentation','alternate')]),
      ('Was first-10 allowance already handled elsewhere?','first_10_prior_work',[('Unknown','unknown'),('No','no'),('Yes','yes')])]
    for label,key,opts in selections:
       row=ttk.Frame(self.finance_tab);row.pack(fill='x',pady=6);ttk.Label(row,text=label,width=43).pack(side='left');v=tk.StringVar(value=self.case.get(key,'unknown'));self.vars[key]=v
       ttk.Combobox(row,textvariable=v,values=[k for _,k in opts],width=18,state='readonly').pack(side='left')
       ttk.Label(row,text=' | '.join(f'{k}={n}' for n,k in opts),foreground='#555').pack(side='left',padx=7)
    ttk.Button(self.finance_tab,text='Confirm first-10-CYD financial rule for this case',command=self.confirm_financial_rule).pack(anchor='w',pady=5)
    ttk.Button(self.finance_tab,text='Recalculate and show exceptions',command=self.show_checks).pack(anchor='w',pady=5)
    self.fin_text=tk.Text(self.finance_tab,height=13,width=110);self.fin_text.pack(fill='both',expand=True)
    self.show_checks()
 def finance_fingerprint(self):
    c=self.case
    keys=['rate_per_cyd','invoice_quantity_cyd','invoice_amount_usd','invoice_deduction_usd','invoice_quantity_basis','invoice_deduction_status','first_10_prior_work','verified_first_10_amount','financial_confirmation_note']
    obj={k:str(c.get(k,'')) for k in keys}
    obj['load_dimensions']=[{k:str(l.get(k,'')) for k in ('length_ft','width_ft','side_height_ft','overage_height_ft','overage_cyd','measured_load_cyd')} for l in c.get('loads',[])]
    return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
 def confirm_financial_rule(self):
    if not self.require():return
    self.sync_case()
    amount=self.case.get('verified_first_10_amount','')
    try:
       n=float(amount)
       if not 0<=n<100000:raise ValueError()
    except (ValueError,TypeError):messagebox.showerror('Invalid amount','Enter a valid first-10-CYD amount.');return
    if any(self.case.get(k,'unknown')=='unknown' for k in ('invoice_quantity_basis','invoice_deduction_status','first_10_prior_work')):
       messagebox.showwarning('Incomplete','Select quantity basis, deduction status and prior-work treatment.');return
    if not self.case.get('financial_confirmation_note','').strip():
       messagebox.showwarning('Source required','Provide the supporting policy or work-order reference.');return
    if messagebox.askyesno('Confirm case-specific deduction',f'Confirm ${n:,.2f} as applicable first-10-CYD amount for {self.case["case_number"]}?\n\nThis is NOT COR approval.'):
       self.case['financial_confirmation_hash']=self.finance_fingerprint();self.save();self.show_checks()
 def transmittal(self):
    if not self.require():return
    self.save()
    pdf=filedialog.askopenfilename(title='Select the reviewed COR package PDF',filetypes=[('PDF','*.pdf')])
    if not pdf:return
    wo=filedialog.askopenfilename(title='Select work order PDF (Cancel to stop)',filetypes=[('PDF','*.pdf')])
    if not wo:return
    approval=filedialog.askopenfilename(title='Select official HUD approval PDF (Cancel to stop)',filetypes=[('PDF','*.pdf')])
    if not approval:return
    if not messagebox.askyesno('Manual transmittal verification','Have you verified the official approval amount and evidence against the COR package?\n\nThis tool combines PDFs; it cannot authenticate approvals.'):
       return
    try:
       import fitz
       out=self.case_dir/'output';out.mkdir(exist_ok=True)
       result=out/(safe(self.case['case_number'])+'_TRANSMITTAL_DRAFT.pdf')
       combined=fitz.open()
       for item in (wo,approval,pdf):
          part=fitz.open(item);combined.insert_pdf(part);part.close()
       combined.save(str(result));combined.close()
       messagebox.showinfo('Transmittal draft',f'Created {result}\n\nReview all pages before sending. Not automatically approved.')
    except Exception as e:messagebox.showerror('Transmittal failed',str(e))
 def audit_evidence(self):
    if not self.require():return
    self.save()
    report=write_report(self.case,self.case_dir/'analysis'/'evidence_audit')
    messagebox.showinfo('Evidence source audit',
        f"Audited {report['assigned_unique_paths']} distinct assigned sources.\n"
        f"Blocking: {report['blocking']}   Review: {report['review']}\n\n"
        'Results saved in analysis/evidence_audit. This is not proof of photo authenticity or correct load stage.')
    self.show_checks()

 def evaluate(self):
    self.sync_case();c=self.case;issues=[];volumes=[]
    for i,l in enumerate(c['loads'],1):
       try: v=volume(l);volumes.append(v['total'])
       except Exception as e:issues.append(f'BLOCKING / Load {i} measurement: {e}');volumes.append(0)
       for key in ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt'):
          if not l.get('photos',{}).get(key):issues.append(f'BLOCKING / Load {i}: missing template image {key}')
       if not l.get('disposal_photo'):issues.append(f'BLOCKING / Load {i}: missing unloading/disposal photo')
       if len(l.get('extra_measurement_photos',[]))<3:issues.append(f'Load {i}: Field Guide supplemental measurement views not fully linked (template remains unchanged)')
       if (as_number(l.get('overage_cyd'))>0 or as_number(l.get('overage_height_ft'))>0) and not l.get('overage_note'):issues.append(f'BLOCKING / Load {i}: overage evidence is not documented')
    if not c['loads'][0].get('evidence_first_10_cyd'):issues.append('BLOCKING / First 10 CYD progression/remaining debris evidence unlinked')
    if not c.get('before_photos') or not c.get('after_photos'):issues.append('BLOCKING / Missing property before and/or after photo selections')
    qty=sum(volumes);rate=as_number(c.get('rate_per_cyd'));gross=qty*rate
    first=c.get('first_10_prior_work','unknown')
    raw=c.get('verified_first_10_amount','')
    try:
       if str(raw).strip()=='':raise ValueError('blank')
       amt=float(raw)
       if not 0<=amt<=gross+0.05:raise ValueError('out of range')
    except (ValueError,TypeError):
       amt=None;issues.append('BLOCKING / Confirm valid first-10-CYD dollar amount for this work order')
    ded=amt if first=='no' else 0 if first=='yes' else None
    if first=='unknown':issues.append('BLOCKING / First-10-CYD prior-work treatment unknown')
    if not c.get('financial_confirmation_note','').strip():issues.append('BLOCKING / Enter rule source or work-order justification')
    if c.get('financial_confirmation_hash','')!=self.finance_fingerprint():
       issues.append('BLOCKING / Financial rule not confirmed, or inputs changed since confirmation')
    basis=c.get('invoice_quantity_basis','unknown');status=c.get('invoice_deduction_status','unknown')
    if basis=='unknown':issues.append('BLOCKING / Confirm whether invoiced quantity includes first 10 CYD')
    if status=='unknown':issues.append('BLOCKING / Confirm whether vendor already applied a deduction')
    invoiceqty=c.get('invoice_quantity_cyd','')
    if invoiceqty in ('',None):issues.append('BLOCKING / Invoiced CYD missing')
    elif basis!='unknown':
       target=qty if basis=='includes' else max(0,qty-10)
       if abs(as_number(invoiceqty,-999)-target)>.1:issues.append(f'BLOCKING / Invoice CYD {as_number(invoiceqty):.2f} vs expected {target:.2f}; investigate')
    shown=c.get('invoice_deduction_usd','')
    if status=='yes':
       if shown in ('',None):issues.append('BLOCKING / Enter deduction actually shown on invoice')
       elif amt is not None and abs(as_number(shown,-999)-amt)>.01:issues.append(f'BLOCKING / Vendor deduction ${as_number(shown):.2f} differs from confirmed ${amt:.2f}')
    if status=='no' and shown not in ('',None) and abs(as_number(shown))>.01:issues.append('BLOCKING / Invoice deduction shown conflicts with selected NO')
    inv=c.get('invoice_amount_usd','')
    if inv in ('',None):issues.append('BLOCKING / Vendor invoice net amount missing')
    elif basis=='includes' and status in ('yes','no'):
       expected=gross-(as_number(shown) if status=='yes' else 0)
       if abs(as_number(inv,-999)-expected)>.06:issues.append(f'BLOCKING / Invoice total differs from stated treatment: expected ${expected:.2f}')
       if status=='no' and ded is not None and ded>0:issues.append('BLOCKING / Deduction missing from invoice; resolve before approval')
    if basis=='excludes':issues.append('REVIEW / Vendor excluded 10 CYD from invoice quantity; verify net amount separately (never double deduct)')
    if status=='alternate':issues.append('REVIEW / Alternate billing needs explicit documentation and financial reviewer approval')
    for finding in audit_evidence(c)['issues']:
       label='BLOCKING' if finding['severity']=='BLOCKING' else 'REVIEW'
       issues.append(f"{label} / Source audit: {finding['detail']}")
    return qty,gross,ded,issues
 def show_checks(self):
    if not self.case:return
    qty,gross,ded,issues=self.evaluate()
    content=f'Measured across all loads: {qty:.2f} CYD\nGross at vendor rate: ${gross:.2f}\nFirst 10 manually verified adjustment: {"UNRESOLVED" if ded is None else f"${ded:.2f}"}\nExpected payable (subject to invoice reconciliation): {"UNRESOLVED" if ded is None else f"${gross-ded:.2f}"}\n\nEXCEPTIONS ({len(issues)})\n'+ ('\n'.join('• '+x for x in issues) if issues else 'No detected checklist exceptions. Human review is still required.')
    if hasattr(self,'fin_text'):self.fin_text.delete('1.0','end');self.fin_text.insert('end',content)
    if hasattr(self,'checks'):self.checks.delete('1.0','end');self.checks.insert('end',content)
    return issues
 def draw_checks(self):
    for w in self.check_tab.winfo_children():w.destroy()
    if not self.case:return
    ttk.Label(self.check_tab,text='Unresolved exceptions prevent automatic COR-ready status.',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=10)
    ttk.Button(self.check_tab,text='Refresh validation',command=self.show_checks).pack(anchor='w')
    self.checks=tk.Text(self.check_tab,height=30,width=125);self.checks.pack(fill='both',expand=True,pady=8)
    self.show_checks()
 def generate(self):
    if not self.require():return
    self.save();qty,gross,ded,issues=self.evaluate()
    fatal=[x for x in issues if x.startswith('BLOCKING')]
    if fatal:
       if not messagebox.askyesno('INCOMPLETE — draft only',f'{len(fatal)} blocking issues found. Generate DRAFT document with review report? It must NOT be submitted to COR.'):
          self.tabs.select(self.check_tab);self.show_checks();return
    folder=self.case_dir/'output';folder.mkdir(exist_ok=True)
    name=safe(self.case['case_number'])+'_ED_Progression_DRAFT.docx';dest=folder/name
    try:
       # Missing dimensions must be repaired before doc generation.
       for l in self.case['loads']:volume(l)
       summary=build(self.case,dest)
       review={'independent_validation':issues,'gross_cyd':qty,'gross_usd':gross,'first_10_adjustment_usd':ded,'expected_payable_usd':(gross-ded if ded is not None else None),'status':'DRAFT — REVIEW REQUIRED','template_builder_report':summary}
       (folder/'ED_Validation_Report.json').write_text(json.dumps(review,indent=2))
       (folder/'ED_Validation_Report.txt').write_text(f'CASE {self.case["case_number"]}\nSTATUS: DRAFT — REVIEW REQUIRED\n\n'+'\n'.join(issues or ['No detected exceptions; verify all source imagery manually.']))
       if shutil.which('libreoffice'):
          subprocess.run(['libreoffice','-env:UserInstallation=file:///tmp/ed_builder2_lo','--headless','--convert-to','pdf','--outdir',str(folder),str(dest)],capture_output=True,timeout=90)
          pdf=dest.with_suffix('.pdf')
          if pdf.exists():
             import fitz
             merged=fitz.open()
             for f in self.case.get('financial_pdfs',[]):
                if Path(f).is_file() and Path(f).suffix.lower()=='.pdf':
                   d=fitz.open(f);merged.insert_pdf(d);d.close()
             d=fitz.open(pdf);merged.insert_pdf(d);d.close()
             merged.save(folder/(safe(self.case['case_number'])+'_ED_COR_DRAFT.pdf'));merged.close()
       if dest.with_suffix('.pdf').exists():
          try:
             import fitz
             with fitz.open(dest.with_suffix('.pdf')) as checkpdf:
                expected=2*len(self.case['loads'])
                if len(checkpdf)<expected:issues.append(f'PDF visual QA: got {len(checkpdf)} pages but at least {expected} progression pages expected')
                (folder/'PDF_Preflight.txt').write_text(f'PDF pages: {len(checkpdf)}\nExpected load progression pages: {expected}\nVisually inspect every final PDF page before COR submission.\n',encoding='utf-8')
          except Exception as e:issues.append(f'PDF QA failed: {e}')
       messagebox.showinfo('Draft generated',f'Draft files saved in:\n{folder}\n\nValidation exceptions: {len(issues)}\nNOT APPROVED FOR COR.')
    except Exception as e:messagebox.showerror('Generate error',str(e))

def packaged_smoke_test(report_path):
    """Headless smoke test of the *packaged executable*; no vendor data accessed."""
    from datetime import datetime, timezone
    from ed_builder import TEMPLATE, make_example, build, volume
    import tempfile
    result = {'status': 'FAIL', 'template_path': str(TEMPLATE), 'template_present': TEMPLATE.is_file(),
              'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'app_frozen': bool(getattr(sys, 'frozen', False))}
    try:
        with tempfile.TemporaryDirectory(prefix='ed_portable_smoke_') as temp:
            temp = Path(temp)
            example = make_example(temp/'case.json')
            example['loads'] = example['loads'][:1]
            doc = temp/'draft.docx'
            review = build(example,doc)
            from docx import Document
            document = Document(doc)
            assert doc.is_file() and doc.stat().st_size > 10000, 'No usable DOCX generated'
            assert len(document.tables) == 2, f'Expected two load tables; got {len(document.tables)}'
            assert len(review['loads']) == 1, 'Load manifest mismatch'
            assert (temp/'calculation_records'/'load_1_calculation.png').is_file(), 'Calculation image missing'
            result.update(status='PASS', tables=len(document.tables), generated_docx_bytes=doc.stat().st_size)
    except Exception as exc:
        result['error']=repr(exc)
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
    sys.exit(packaged_smoke_test(sys.argv[2]))
 BASE.mkdir(exist_ok=True)
 root=tk.Tk();app=App(root);root.mainloop()
