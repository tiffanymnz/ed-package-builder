"""Resumable local vision trial. Suggestions are never evidence assignments."""
import hashlib
import json
import os
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from calculator_evidence import file_digest

LABELS={'property_before':'Property Before Removal','property_during':'Property During Removal','property_after':'Property After Removal',
 'measurement':'Measurements','container_empty':'Empty Container','container_quarter':'Quarter-Full Container',
 'container_half':'Half-Full Container','container_three_quarters':'Three-Quarter-Full Container','container_full':'Full Container',
 'dump_receipt':'Dump Receipts','disposal_unloading':'Unloading / Disposal','invoice':'Invoices','bid':'Bids','estimate':'Cost Estimates','other':'Other','unclear':'Unclear'}
LABELS.update({'documents':'Documents (Confirm Purpose)','container_photos':'Container Photos','property_photos':'Property Photos'})
BROAD_CATEGORIES=['invoice','bid','dump_receipt','measurement','container_photos','property_photos','other','unclear']
PROMPT='Look at the image. Classify the visible object, not the service described in its text. Categories: invoice (a bill requesting payment), bid (a price quote or estimate), dump_receipt (a disposal or scale ticket), measurement (a tape measure or dimensions), container_photos (a truck, trailer or dumpster), property_photos (a yard, building, land or debris at a property), other, unclear. A paper invoice about debris removal is invoice, NOT property_photos. Return category, load_number as null unless a load number is readable, and a short reason.'
VERSION=hashlib.sha256((PROMPT+';category-head-1-v26;property-stage-1-v41;measurement-controls-1').encode()).hexdigest()

from small_vision_runtime import RUNTIME, MODEL_ID, MODEL_DIGEST, SetupCancelled

def installed_models():
    return [dict(name=MODEL_ID,digest=MODEL_DIGEST)] if RUNTIME.ready() else []

def parse_prediction(raw):
    if isinstance(raw,str):
        raw=raw.strip()
        if raw.startswith('```'):raw=raw.split('\n',1)[-1].rsplit('```',1)[0]
        raw=json.loads(raw)
    if not isinstance(raw,dict):raise ValueError('Model response was not an object.')
    category=raw.get('category','unclear')
    if category not in LABELS:category='unclear'
    number=raw.get('load_number')
    if not isinstance(number,int) or isinstance(number,bool) or not 1<=number<=150:number=None
    return dict(category=category,load_number=number,reason=str(raw.get('reason',''))[:500],verified=False)

def analyze(path,model):
    if model!=dict(name=MODEL_ID,digest=MODEL_DIGEST):raise RuntimeError('Unsupported photo model.')
    return RUNTIME.classify(path)

def read_cache(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def save_cache(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.pending');temp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(temp,path)

def batch(records,model,cache_path,cancel,on_result,limit=None,infer=analyze):
    from review_assist import image_features,FEATURE_VERSION
    cache=read_cache(cache_path);done=0;reused=0;new_calls=0;dirty=0;started=time.monotonic();by_content={}
    for row in cache.values():
        if row.get('model_digest')==model['digest'] and row.get('prompt_version')==VERSION:by_content[row.get('sha256')]=row
    try:
        for record in records:
            if cancel.is_set():break
            path=record['path'];digest=file_digest(path);row=cache.get(path,{})
            valid=row.get('sha256')==digest and row.get('model_digest')==model['digest'] and row.get('prompt_version')==VERSION
            changed=False
            if not valid:
                previous=by_content.get(digest)
                from review_assist import decode_embedding
                old_vector=decode_embedding(row) if row.get('sha256')==digest and row.get('model_digest')==model['digest'] else None
                if old_vector is not None:
                    from photo_category_head import predict_category,image_has_content
                    prediction=dict(row['prediction'],**predict_category(old_vector),load_number=None,verified=False)
                    if not image_has_content(path):prediction['category']='unclear'
                    reused+=1
                elif previous:
                    prediction=previous['prediction'];reused+=1
                else:
                    if limit is not None and new_calls>=limit:break
                    prediction=infer(path,model);new_calls+=1
                # Features from an older version of the file cannot be reused.
                row=dict(row) if row.get('sha256')==digest else {}
                row.update(sha256=digest,model=model['name'],model_digest=model['digest'],prompt_version=VERSION,prediction=prediction)
                changed=True
            else:reused+=1
            if row.get('features',{}).get('version')!=FEATURE_VERSION:
                row=dict(row,features=image_features(path));changed=True
            if file_digest(path)!=digest:raise RuntimeError('A photo changed during processing. Run the batch again.')
            if changed:
                cache[path]=row;by_content[digest]=row;dirty+=1
                if dirty>=10:save_cache(cache_path,cache);dirty=0
            done+=1;on_result(path,row,done,len(records),time.monotonic()-started,reused)
    finally:
        if dirty:save_cache(cache_path,cache)
    return dict(processed=done,reused=reused,cancelled=cancel.is_set())

def suggested_category(case,path):
    row=case.get('local_photo_results',{}).get(path,{})
    try:
        if row.get('prompt_version')!=VERSION or row.get('model_digest')!=MODEL_DIGEST or row.get('sha256')!=file_digest(path):return 'Not Analyzed'
        return LABELS.get(row.get('prediction',{}).get('category'),'Unclear')
    except OSError:return 'Not Analyzed'

class LocalPhotoSorterWindow:
    def __init__(self,app):
        self.app=app;self.case=app.case;self.directory=Path(app.case_dir);self.events=queue.Queue();self.cancel=threading.Event();self.running=False;self.models=[];self.closed=False
        self.cache_path=self.directory/'local_photo_sorting.json'
        self.case['local_photo_results']=read_cache(self.cache_path)
        self.win=tk.Toplevel(app.root);self.win.title('Organize Photos Locally');self.win.geometry('740x430');self.win.transient(app.root)
        body=ttk.Frame(self.win,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Organize Photos Locally',font=(app.ui_font,19,'bold')).pack(anchor='w')
        ttk.Label(body,text='Start with 5 photos. This small model suggests broad categories. Before / During / After and load assignments still need your review.',wraplength=670).pack(anchor='w',pady=12)
        row=ttk.Frame(body);row.pack(fill='x');self.model=tk.StringVar(value=MODEL_ID)
        self.setup_button=ttk.Button(row,text='Set Up Photo Sorting',style='Primary.TButton',command=self.setup);self.setup_button.pack(side='left')
        ttk.Label(row,text='One-time model download: about 90 MB. No separate installer.',style='Muted.TLabel',wraplength=420).pack(side='left',padx=12)
        row=ttk.Frame(body);row.pack(fill='x',pady=10);ttk.Label(row,text='New Photos This Run').pack(side='left')
        self.count=tk.StringVar(value='5');ttk.Combobox(row,textvariable=self.count,values=['5','20','100','All'],state='readonly',width=9).pack(side='left',padx=10)
        self.status=tk.StringVar(value='Checking photo sorting...');ttk.Label(body,textvariable=self.status,wraplength=670).pack(anchor='w',pady=12)
        self.progress=ttk.Progressbar(body,maximum=1);self.progress.pack(fill='x',pady=8)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=10)
        self.start_button=ttk.Button(actions,text='Organize Photos',style='Primary.TButton',command=self.start);self.start_button.pack(side='left')
        ttk.Button(actions,text='Stop',command=self.cancel.set).pack(side='left',padx=8)
        ttk.Button(actions,text='Review Results',command=self.review).pack(side='right')
        ttk.Button(body,text='Remove Photo Sorting Files',command=self.remove).pack(anchor='w',pady=(4,0))
        self.app._photo_sorting_windows=getattr(self.app,'_photo_sorting_windows',[])+[self]
        self.win.protocol('WM_DELETE_WINDOW',self.close);self.poll_job=self.win.after(100,self.poll);self.discover()

    def discover(self):
        if self.running:return
        self.models=installed_models()
        if self.models:
            self.model.set(self.models[0]['name']);self.setup_button.configure(text='Photo Sorting Is Ready')
            self.status.set('Ready. The local engine starts automatically when you organize photos.')
        else:self.status.set('Choose Set Up Photo Sorting once. Your case photos are not uploaded.')

    def setup(self):
        if self.running:return
        self.running=True;self.cancel.clear();self.start_button.configure(state='disabled');self.setup_button.configure(state='disabled')
        def work():
            try:
                RUNTIME.setup(self.cancel,lambda *values:self.events.put(('setup_progress',values)))
                self.events.put(('setup_done',None))
            except SetupCancelled:self.events.put(('setup_stopped',None))
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.running=False
        threading.Thread(target=work,daemon=True).start()

    def remove(self):
        if self.running:messagebox.showinfo('Stop First','Stop photo processing or setup before removing its files.',parent=self.win);return
        if not messagebox.askyesno('Remove Photo Sorting','Remove the downloaded engine and model to reclaim their storage? Your case photos, documents and reviewed assignments will stay saved.',parent=self.win):return
        try:RUNTIME.remove();self.models=[];self.setup_button.configure(text='Set Up Photo Sorting');self.discover()
        except Exception as exc:messagebox.showerror('Cannot Remove Files',str(exc),parent=self.win)

    def start(self):
        if self.running:return
        model=next((m for m in self.models if m['name']==self.model.get()),None)
        if not model:messagebox.showinfo('Set Up Photo Sorting','Choose Set Up Photo Sorting first. No separate application needs to be installed.',parent=self.win);return
        records=[dict(r) for r in self.case.get('imported_files',[]) if Path(r['path']).suffix.lower() in {'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}]
        if not records:self.status.set('Import photos first.');return
        self.running=True;self.start_button.configure(state='disabled');self.setup_button.configure(state='disabled');self.cancel.clear();limit=None if self.count.get()=='All' else int(self.count.get())
        self.status.set('Starting local photo sorting. The model loads on this computer. Stop waits for the current photo to finish.')
        def work():
            try:
                result=batch(records,model,self.cache_path,self.cancel,lambda *values:self.events.put(('result',values)),limit)
                self.events.put(('done',result))
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.running=False
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if self.closed:return
        if self.poll_job:self.win.after_cancel(self.poll_job);self.poll_job=None
        changed=False
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='setup_progress':
                message,done,total=value;self.status.set(message);self.progress.configure(maximum=max(1,total),value=done)
            elif kind in ('setup_done','setup_stopped'):
                self.running=False;self.start_button.configure(state='normal');self.setup_button.configure(state='normal')
                self.discover()
                if kind=='setup_stopped':self.status.set('Setup stopped. Choose Set Up Photo Sorting to resume the download.')
            elif kind=='result':
                path,row,done,total,elapsed,reused=value
                if self.app.case is self.case:self.case.setdefault('local_photo_results',{})[path]=row;changed=True
                self.progress.configure(maximum=total,value=done)
                self.status.set(f'{done} of {total} photos checked · {reused} cached · {elapsed:.0f} seconds. Suggestions await review.')
            elif kind in ('done','error'):
                self.running=False;self.start_button.configure(state='normal');self.setup_button.configure(state='normal')
                if kind=='done':self.status.set(f"{'Stopped' if value['cancelled'] else 'Finished'}: {value['processed']} photos checked. Open Review Results. Saved results can be reused on the next run.")
                else:self.status.set('Processing stopped: '+str(value)[:250]+' No cloud fallback was used.')
        if changed:self.app.save()
        self.poll_job=self.win.after(150,self.poll)

    def review(self):
        if self.app.case is not self.case:return
        self.case['local_photo_results']=read_cache(self.cache_path);self.app.save()
        from visual_photo_review import PhotoReviewWindow
        gallery=PhotoReviewWindow(self.app);gallery.best_only.set(True);gallery.group_by.set('Suggested Category');gallery.update_groups()

    def close(self):
        self.cancel.set();self.closed=True
        if self.poll_job:self.win.after_cancel(self.poll_job);self.poll_job=None
        if self.app.case is self.case:self.case['local_photo_results']=read_cache(self.cache_path);self.app.save()
        self.win.destroy()
