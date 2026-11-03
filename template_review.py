"""Template-first photo shortlists. All evidence choices remain explicit."""
import copy
import hashlib
import math
from datetime import datetime,timezone
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageOps,ImageTk
from calculator_evidence import file_digest
from cor_package import photo_suggestion
from review_assist import checked_rows,decode_embedding,valid_features
from template_slot_head import predict_slots

SLOTS=[('calculator','Cubic Yard Calculation'),('height','Height Measurement'),
       ('width','Width Measurement'),('length','Length Measurement'),('empty','Empty Container'),
       ('quarter','Quarter Full'),('half','Half Full'),('three_quarters','Three Quarters Full'),
       ('full_1','Full Container — View 1'),('full_2','Full Container — View 2'),
       ('receipt','Dump Receipt'),('disposal_photo','Unloading / Disposal'),
       ('first_10_proof','First 10 CYD Evidence')]
IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
CORE={key for key,_ in SLOTS if key not in ('calculator','disposal_photo','first_10_proof')}
DOCUMENT_ROLES={'invoice','bid','estimate','approval','work_order','hpir'}
BOX_HELP={
    'calculator':'Confirm this load’s measurements in Container Details, then attach its cubic yard calculation screenshot.',
    'height':'Choose a clear photo of the container height measurement. Check that the tape markings and both endpoints are visible.',
    'width':'Choose a clear photo measuring across the container. Check the tape markings and both endpoints; do not confuse width with length.',
    'length':'Choose a clear photo measuring along the container. Check the tape markings and both endpoints; do not confuse length with width.',
    'empty':'Choose the container before loading, with its interior visibly empty. This is different from a before photo of debris at the property.',
    'quarter':'Choose this load at about one-quarter full. Compare nearby loading photos if the amount is unclear.',
    'half':'Choose this load at about half full. Compare nearby loading photos if the amount is unclear.',
    'three_quarters':'Choose this load at about three-quarters full. Compare nearby loading photos if the amount is unclear.',
    'full_1':'Choose a clear view of this load when full, showing the container and debris level.',
    'full_2':'Choose a different view of the same full load. Use it to show details the first view does not show.',
    'receipt':'Choose the readable dump receipt for this load. Check the load details and date against the other evidence.',
    'disposal_photo':'Choose a photo showing this load being unloaded or disposed of at the disposal location.',
    'first_10_proof':'Choose evidence documenting the first 10 CYD removed. Check it alongside the remaining-debris and loading photos.'}

def measurement_view_clues(path):
    """Weak tape-like line cues for ranking only, never a dimension reading."""
    import cv2
    import numpy as np
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((640,640));pixels=np.asarray(image)
    hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([15,65,85]),np.array([42,255,255]))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    horizontal=vertical=0
    for contour in contours:
        rect=cv2.minAreaRect(contour);lo,hi=sorted(rect[1]);area=cv2.contourArea(contour)
        if lo<=0 or hi/lo<5 or hi/max(pixels.shape[:2])<.25 or area/(pixels.shape[0]*pixels.shape[1])<.001:continue
        points=cv2.boxPoints(rect);edges=np.roll(points,-1,axis=0)-points
        edge=edges[np.linalg.norm(edges,axis=1).argmax()]
        strength=min(1,(hi/lo-4)/8)*min(1,hi/max(pixels.shape[:2])/.5)
        if abs(edge[0])>=abs(edge[1]):horizontal=max(horizontal,strength)
        else:vertical=max(vertical,strength)
    return dict(horizontal=float(horizontal),vertical=float(vertical))

def assigned_path(load,slot):
    if slot=='calculator':return load.get('calculator_evidence',{}).get('path','')
    if slot=='disposal_photo':return load.get(slot,'')
    if slot=='first_10_proof':return load.get('evidence_first_10_cyd','')
    return load.get('photos',{}).get(slot,'')

def assignments(case):
    result=[]
    for n,load in enumerate(case.get('loads',[]),1):
        for slot,_ in SLOTS:
            path=assigned_path(load,slot)
            if path:result.append((n,slot,path))
    return result

def pixel_digest(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB')
        return hashlib.sha256(f'{image.width}x{image.height}:'.encode()+image.tobytes()).hexdigest()

class TemplateCandidateIndex:
    def __init__(self,case):
        from local_photo_sorter import MODEL_DIGEST,VERSION
        self.records=list({r['path']:r for r in case.get('imported_files',[]) if Path(r['path']).suffix.lower() in IMAGE_EXT}.values())
        cache=dict(case.get('local_photo_results',{}))
        for path,entry in case.get('photo_text_cache',{}).items():
            if path not in cache and entry.get('sha256'):cache[path]={'sha256':entry['sha256']}
        self.rows=checked_rows(self.records,cache,MODEL_DIGEST,VERSION)
        self.scores={};self.text={};self.geometry={}
        for record in self.records:
            path=record['path'];row=self.rows.get(path,{});vector=decode_embedding(row)
            detail=row.get('features',{}).get('detail')
            blank=isinstance(detail,(int,float)) and detail<2
            if vector is not None and not blank:self.scores[path]=predict_slots(vector)
            scores=self.scores.get(path,{})
            if any(scores.get(key,0)>=.15 and scores.get(key,0)>scores.get('other',0) for key in ('height','width','length')):
                previous=case.get('template_geometry_cache',{}).get(path,{})
                if previous.get('sha256')==row.get('sha256') and previous.get('version')==1 and all(isinstance(previous.get(k),(int,float)) and math.isfinite(previous[k]) and 0<=previous[k]<=1 for k in ('horizontal','vertical')):
                    self.geometry[path]=previous
                else:
                    try:self.geometry[path]=dict(measurement_view_clues(path),sha256=row['sha256'],version=1)
                    except (OSError,ValueError):pass
            text=case.get('photo_text_cache',{}).get(path,{})
            if row.get('sha256') and text.get('sha256')==row['sha256']:self.text[path]=photo_suggestion(record,text.get('text',''))

    def shortlist(self,case,load_number,slot,browse_all=False,offset=0,limit=3):
        target='full' if slot in ('full_1','full_2') else slot
        used=assignments(case);candidates=[]
        for record in self.records:
            path=record['path'];row=self.rows.get(path,{});digest=row.get('sha256')
            financial=any(d.get('confirmed') and d.get('path')==path and d.get('role') in DOCUMENT_ROLES for d in case.get('package_documents',[]))
            if financial and not browse_all:continue
            places=[(n,s) for n,s,p in used if p==path or (digest and self.rows.get(p,{}).get('sha256')==digest)]
            tag=case.get('photo_load_assignments',{}).get(path,{})
            manual_load=tag.get('load') if digest and tag.get('sha256')==digest else None
            if any(n!=load_number for n,s in places) or (manual_load and manual_load!=load_number):continue
            if not browse_all and any(s!=slot and s in CORE for n,s in places):continue
            text=self.text.get(path,{});text_load=text.get('load')
            if not browse_all and text_load and text_load!=load_number:continue
            scores=self.scores.get(path,{});score=scores.get(target,0)
            visual=bool(score>=.15 and score>scores.get('other',0) and target in sorted(scores,key=scores.get,reverse=True)[:3])
            direct=bool(text.get('slot')==slot and slot!='calculator')
            reviewed=case.get('photo_category_examples',{}).get(path,{})
            expected='measurement' if slot in ('height','width','length') else 'documents' if slot=='receipt' else 'container_photos'
            category_conflict=bool(digest and reviewed.get('sha256')==digest and reviewed.get('category')!=expected)
            if not browse_all and (category_conflict or not (visual or direct)):continue
            try:
                quality=float(row.get('features',{}).get('quality',0))/10
                quality=max(0,min(1,quality)) if math.isfinite(quality) else 0
            except (ValueError,TypeError):quality=0
            rank=(2 if direct else 0)+score+.025*quality+(.03 if manual_load==load_number or text_load==load_number else 0)
            if slot in ('height','width','length'):
                axis='vertical' if slot=='height' else 'horizontal'
                rank+=.10*self.geometry.get(path,{}).get(axis,0)
            clue=f'Reviewed Load {manual_load}' if manual_load else f'Photo Text: Load {text_load}' if text_load else 'Load Not Confirmed'
            candidates.append(dict(path=path,name=record.get('name',Path(path).name),sha256=digest,
                                   rank=rank,basis='Photo Text Suggestion' if direct else 'Visual Candidate' if visual else 'Browse Original',
                                   load_clue=clue,text_load=text_load))
        candidates.sort(key=lambda r:(-r['rank'],r['path']))
        distinct=[];seen=set()
        for row in candidates:
            feature=self.rows.get(row['path'],{}).get('features',{})
            key=(feature.get('pixel_hash') if valid_features(feature) else None) or row['sha256'] or row['path']
            if key in seen:continue
            seen.add(key);distinct.append(row)
        return distinct[offset:offset+limit],len(distinct)

def assign_template_photo(case,load_number,slot,candidate):
    if slot not in CORE|{'disposal_photo','first_10_proof'}:raise ValueError('Use Attach Calculation for a calculation screenshot.')
    if not 1<=load_number<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
    path=candidate['path']
    if path not in {r['path'] for r in case.get('imported_files',[])}:raise ValueError('Import the source photo first.')
    if any(d.get('confirmed') and d.get('path')==path and d.get('role') in DOCUMENT_ROLES for d in case.get('package_documents',[])):
        raise ValueError('This file is already a reviewed package document. Choose the actual evidence photo, or correct its document purpose first.')
    digest=file_digest(path)
    if not candidate.get('sha256') or digest!=candidate['sha256']:raise ValueError('This photo changed. Refresh the suggestions and inspect it again.')
    with Image.open(path) as image:image.verify()
    tag=case.get('photo_load_assignments',{}).get(path,{})
    if tag.get('sha256')==digest and tag.get('load') not in (None,load_number):raise ValueError('This photo belongs to another reviewed load. Correct that load assignment first.')
    for n,other_slot,other_path in assignments(case):
        if other_path==path:identical=True
        else:
            try:identical=file_digest(other_path)==digest
            except OSError:identical=False
        if identical and n!=load_number:raise ValueError('This source is already assigned to another load. Check the original load evidence.')
        if n==load_number and {slot,other_slot}=={'full_1','full_2'} and not identical:
            try:identical=pixel_digest(path)==pixel_digest(other_path)
            except OSError:pass
        if identical and {slot,other_slot}=={'full_1','full_2'}:raise ValueError('Choose a different photograph for the second full-container view.')
    load=case['loads'][load_number-1];previous=assigned_path(load,slot)
    if slot=='disposal_photo':load[slot]=path
    elif slot=='first_10_proof':load['evidence_first_10_cyd']=path
    else:load.setdefault('photos',{})[slot]=path
    if previous!=path and slot in ('height','width','length'):load['measurements_confirmed']=False
    case.setdefault('template_photo_reviews',{})[f'{load_number}:{slot}']=dict(path=path,sha256=digest,load=load_number,slot=slot,
        selected_at=datetime.now(timezone.utc).isoformat(),basis='Selected by the user in template photo review.')

class TemplateReviewWindow:
    def __init__(self,app):
        self.app=app;self.case=app.case;self.index=None;self.page=0;self.images=[];self.closed=False;self.results=queue.Queue();self.poll_job=None;self.resize_job=None
        self.win=tk.Toplevel(app.root);self.win.title('Review Suggested Photos')
        self.win.geometry(f'1100x{max(600,min(800,app.root.winfo_screenheight()-80))}');self.win.minsize(900,600);self.win.transient(app.root)
        body=ttk.Frame(self.win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Review Suggested Photos',font=(app.ui_font,20,'bold')).pack(anchor='w')
        ttk.Label(body,text='1. Choose the load and a box on the left.  2. Check the suggested photos.  3. Select Use This Photo to save and continue.',wraplength=850).pack(anchor='w',pady=(5,12))
        controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,12));ttk.Label(controls,text='Load').pack(side='left')
        self.load=tk.IntVar(value=int(app.e_load.get()));combo=ttk.Combobox(controls,textvariable=self.load,values=list(range(1,len(self.case['loads'])+1)),state='readonly',width=6);self.load_box=combo;combo.pack(side='left',padx=8)
        combo.bind('<<ComboboxSelected>>',lambda event:self.change_load())
        ttk.Button(controls,text='+ Add Load',command=self.add_load).pack(side='left',padx=(0,8))
        ttk.Button(controls,text='Refresh Suggestions',command=self.refresh).pack(side='left')
        ttk.Button(controls,text='Run Local Photo Sorting',command=app.local_ai_review).pack(side='right')
        self.browse=tk.BooleanVar(value=False);ttk.Checkbutton(controls,text='Browse All Originals',variable=self.browse,command=self.reset_page).pack(side='right',padx=8)
        foot=ttk.Frame(body);foot.pack(side='bottom',fill='x',pady=(12,0))
        self.status=ttk.Label(foot,text='Preparing suggestions...',wraplength=760);self.status.pack(side='left')
        ttk.Button(foot,text='Done',command=self.close).pack(side='right')
        content=ttk.Frame(body);content.pack(fill='both',expand=True)
        left=ttk.Frame(content);left.pack(side='left',fill='y',padx=(0,14))
        self.progress=ttk.Label(left,text='');self.progress.pack(side='bottom',anchor='w',pady=(8,0))
        tree_frame=ttk.Frame(left);tree_frame.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(tree_frame,columns=('status',),show='tree headings',height=10,selectmode='browse')
        self.tree.heading('#0',text='Template Box');self.tree.column('#0',width=195,minwidth=150)
        self.tree.heading('status',text='Status');self.tree.column('status',width=72,minwidth=55)
        scroll=ttk.Scrollbar(tree_frame,orient='vertical',command=self.tree.yview)
        scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',lambda event:self.reset_page())
        right=ttk.Frame(content);right.pack(side='left',fill='both',expand=True)
        self.heading=ttk.Label(right,text='',font=(app.ui_font,15,'bold'));self.heading.pack(anchor='w')
        self.box_help=ttk.Label(right,text='',wraplength=500);self.box_help.pack(anchor='w',pady=(6,0))
        current=ttk.Frame(right);current.pack(fill='x',pady=(8,10))
        self.current=ttk.Label(current,text='',wraplength=470);self.current.pack(side='left')
        ttk.Button(current,text='Open Selected Photo',command=self.open_current).pack(side='right')
        self.cards=ttk.Frame(right)
        paging=ttk.Frame(right);self.paging=paging;paging.pack(side='bottom',fill='x',pady=(10,0));ttk.Button(paging,text='Previous Photos',command=lambda:self.move(-1)).pack(side='left')
        self.page_label=ttk.Label(paging,text='');self.page_label.pack(side='left',padx=10)
        ttk.Button(paging,text='Next Photos',command=lambda:self.move(1)).pack(side='right')
        ttk.Button(paging,text='Read Load Clues',command=self.read_load_clues).pack(side='right',padx=6)
        self.cards.pack(fill='both',expand=True)
        self.win.protocol('WM_DELETE_WINDOW',self.close);self.refresh_tree();self.refresh()
        def resize(event):
            if event.widget is not self.win or self.closed:return
            if self.resize_job:self.win.after_cancel(self.resize_job)
            self.resize_job=self.win.after(120,self.render)
        self.win.bind('<Configure>',resize)
        self.win.bind('<Destroy>',lambda event:self.cleanup() if event.widget is self.win else None)

    def slot(self):return self.tree.selection()[0] if self.tree.selection() else 'height'
    def refresh_tree(self,select=None):
        previous=select or self.slot();self.tree.delete(*self.tree.get_children())
        load=self.case['loads'][self.load.get()-1]
        for key,label in SLOTS:
            path=assigned_path(load,key);status='Selected' if path and Path(path).is_file() else 'Missing'
            self.tree.insert('','end',iid=key,text=label,values=(status,))
        selected=sum(bool(assigned_path(load,key) and Path(assigned_path(load,key)).is_file()) for key,_ in SLOTS)
        self.progress.configure(text=f'{selected} of {len(SLOTS)} boxes selected')
        self.tree.selection_set(previous);self.tree.see(previous)
    def change_load(self):self.app.e_load.set(str(self.load.get()));self.refresh_tree();self.reset_page()
    def add_load(self):
        if self.app.case is not self.case:self.close();return
        self.app.add_load();self.app.save();self.load.set(len(self.case['loads']));self.app.e_load.set(str(self.load.get()));self.refresh()
    def refresh(self):
        if self.closed or self.app.case is not self.case:return
        self.status.configure(text='Preparing suggestions locally...');self.index=None
        self.load_box.configure(values=list(range(1,len(self.case['loads'])+1)))
        self.refresh_tree()
        snapshot=copy.deepcopy(self.case);request=object();self.request=request
        def work():
            try:self.results.put((request,TemplateCandidateIndex(snapshot),None))
            except Exception as exc:self.results.put((request,None,str(exc)))
        threading.Thread(target=work,daemon=True).start();self.schedule_poll(request)
    def schedule_poll(self,request):
        if self.poll_job:self.win.after_cancel(self.poll_job)
        self.poll_job=self.win.after(100,lambda:self.poll(request))
    def poll(self,active_request):
        self.poll_job=None
        if self.closed or not self.win.winfo_exists() or active_request is not self.request:return
        if self.results.empty():self.schedule_poll(active_request);return
        request,index,error=self.results.get()
        if request is not self.request:self.schedule_poll(active_request);return
        if self.app.case is not self.case:self.close();return
        if error:self.status.configure(text='Suggestions unavailable: '+error);return
        self.index=index
        for path,entry in index.geometry.items():
            row=self.case.get('local_photo_results',{}).get(path,{})
            if row.get('sha256')==entry['sha256']:self.case.setdefault('template_geometry_cache',{})[path]=entry
        self.reset_page()
    def reset_page(self):self.page=0;self.render()
    def move(self,amount):self.page=max(0,self.page+amount);self.render()
    def open_current(self):self.app.open_original(assigned_path(self.case['loads'][self.load.get()-1],self.slot()))
    def container_details(self):
        self.app.e_load.set(str(self.load.get()));self.app.measurements()
    def read_load_clues(self):
        if self.closed or self.app.case is not self.case or self.index is None:return
        if self.app.scan_running:
            self.status.configure(text='Photo text reading is already running. Refresh the suggestions when it finishes.');return
        rows,total=self.index.shortlist(self.case,self.load.get(),self.slot(),self.browse.get(),self.page*3,3)
        paths={row['path'] for row in rows}
        records=[record for record in self.index.records if record['path'] in paths]
        if not records:return
        self.status.configure(text='Reading load clues in these photos locally... No photo will be assigned automatically.')
        def done():
            if not self.closed and self.app.case is self.case:self.refresh()
        self.app.scan_photos(records,on_complete=done)
    def render(self):
        if self.closed or self.app.case is not self.case:return
        for child in self.cards.winfo_children():child.destroy()
        self.images=[];slot=self.slot();n=self.load.get();label=dict(SLOTS)[slot]
        self.heading.configure(text=f'Load {n} · {label}')
        self.box_help.configure(text=BOX_HELP.get(slot,''),wraplength=max(350,self.cards.winfo_width()-10))
        selected=assigned_path(self.case['loads'][n-1],slot)
        self.current.configure(text='Selected: '+Path(selected).name if selected else 'No photo selected for this box.')
        if slot=='calculator':
            self.paging.pack_forget()
            ttk.Label(self.cards,text='Attach the actual cubic yard calculation after confirming this load’s measurements.',wraplength=500).pack(anchor='w',pady=15)
            ttk.Button(self.cards,text='Container Details',command=self.container_details).pack(anchor='w',pady=(0,10))
            ttk.Button(self.cards,text='Attach Calculation',command=lambda:self.app.attach_calculator(n-1)).pack(anchor='w');return
        if not self.paging.winfo_manager():self.paging.pack(side='bottom',fill='x',pady=(10,0),before=self.cards)
        if self.index is None:return
        candidates,total=self.index.shortlist(self.case,n,slot,self.browse.get(),self.page*3,3)
        if self.page and not candidates:self.page=max(0,(total-1)//3);return self.render()
        self.page_label.configure(text=f'{self.page+1} / {max(1,(total+2)//3)}')
        self.status.configure(text='Check that the photo belongs to this load. Wrong suggestions? Use Next Photos or Browse All Originals. You can leave a box empty and return later.')
        if not candidates:
            ttk.Label(self.cards,text='No useful suggestion for this box yet. Try Browse All Originals, or run local photo sorting and refresh.',wraplength=500).pack(anchor='w',pady=20);return
        for column,candidate in enumerate(candidates):
            preview_width=max(95,min(195,(self.cards.winfo_width()-30)//3-20))
            preview_height=max(60,min(215,self.cards.winfo_height()-210))
            card=ttk.Frame(self.cards,style='Card.TFrame',padding=9);card.grid(row=0,column=column,sticky='nsew',padx=3);self.cards.columnconfigure(column,weight=1,uniform='candidate')
            self.cards.rowconfigure(0,weight=1)
            actions=ttk.Frame(card,style='Card.TFrame');actions.pack(side='bottom',fill='x',pady=(8,0))
            ready=False
            try:
                digest=file_digest(candidate['path'])
                if candidate['sha256'] and digest!=candidate['sha256']:raise ValueError('Photo changed — refresh suggestions.')
                candidate=dict(candidate,sha256=digest)
                with Image.open(candidate['path']) as source:
                    image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((preview_width,preview_height));preview=ImageTk.PhotoImage(image)
                self.images.append(preview);ttk.Label(card,image=preview,style='Card.TLabel').pack(pady=6);ready=True
            except Exception as exc:ttk.Label(card,text=str(exc),wraplength=preview_width).pack()
            name=candidate['name'];display_name=name if len(name)<=30 else name[:12]+'…'+name[-15:]
            ttk.Label(card,text=display_name,wraplength=preview_width,style='Card.TLabel').pack(anchor='w',pady=5)
            ttk.Label(actions,text=candidate['load_clue'],wraplength=preview_width,style='Card.TLabel').pack(anchor='w',pady=(0,4))
            ttk.Button(actions,text='Open Full Photo',command=lambda p=candidate['path']:self.app.open_original(p)).pack(fill='x',pady=4)
            ttk.Button(actions,text='Use This Photo',style='Primary.TButton',state='normal' if ready else 'disabled',command=lambda c=candidate:self.use(c)).pack(fill='x',pady=4)
    def use(self,candidate):
        if self.app.case is not self.case:self.close();return
        n=self.load.get();slot=self.slot()
        if candidate.get('text_load') not in (None,n) and not messagebox.askyesno('Check Load Number',f'Photo text suggests Load {candidate["text_load"]}. Have you checked that it belongs in Load {n}?',parent=self.win):return
        old=assigned_path(self.case['loads'][n-1],slot)
        if old and old!=candidate['path'] and not messagebox.askyesno('Replace Selected Photo',f'Replace the selected {dict(SLOTS)[slot].lower()} photo for Load {n}?',parent=self.win):return
        try:
            assign_template_photo(self.case,n,slot,candidate);self.app.save();self.app.refresh_assignments()
            keys=[key for key,_ in SLOTS];following=keys[keys.index(slot)+1:]+keys[:keys.index(slot)]
            next_slot=next((key for key in following if key!='calculator' and not assigned_path(self.case['loads'][n-1],key)),slot)
            self.browse.set(False);self.refresh_tree(next_slot);self.reset_page()
        except Exception as exc:messagebox.showwarning('Photo Not Assigned',str(exc),parent=self.win)
    def close(self):
        if self.closed:return
        self.cleanup();self.win.destroy()
    def cleanup(self):
        self.closed=True
        for job in (self.poll_job,self.resize_job):
            if job:
                try:self.win.after_cancel(job)
                except tk.TclError:pass
        self.poll_job=self.resize_job=None
