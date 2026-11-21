from ui_windows import fit_window
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
        self.scores={};self.text={};self.geometry={};self.semantics={};self.card_claims={}
        for record in self.records:
            path=record['path'];row=self.rows.get(path,{});vector=decode_embedding(row)
            detail=row.get('features',{}).get('detail')
            blank=isinstance(detail,(int,float)) and detail<2
            if vector is not None and not blank:self.scores[path]=predict_slots(vector)
            from photo_semantics import scores as semantic_scores
            self.semantics[path]=semantic_scores(row)
            scores=self.scores.get(path,{})
            if any(scores.get(key,0)>=.15 and scores.get(key,0)>scores.get('other',0) for key in ('height','width','length')) or self.semantics[path].get('container_measurement',0)>.24:
                previous=case.get('template_geometry_cache',{}).get(path,{})
                if previous.get('sha256')==row.get('sha256') and previous.get('version')==1 and all(isinstance(previous.get(k),(int,float)) and math.isfinite(previous[k]) and 0<=previous[k]<=1 for k in ('horizontal','vertical')):
                    self.geometry[path]=previous
                else:
                    try:self.geometry[path]=dict(measurement_view_clues(path),sha256=row['sha256'],version=1)
                    except (OSError,ValueError):pass
            text=case.get('photo_text_cache',{}).get(path,{})
            if row.get('sha256') and text.get('sha256')==row['sha256']:self.text[path]=photo_suggestion(record,text.get('text',''))

        from card_evidence import stage_claim
        self.card_claims={r['path']:claim for r in self.records if (claim:=stage_claim(case,r['path']))}
        self.groups={}
        if case.get('load_card_reviews'):
            from photo_flow import build_photo_rows
            from load_groups import propose_groups
            group_rows,group_checked=build_photo_rows(case);self.groups={p:g for p,g in propose_groups(dict(case,local_photo_results=group_checked),group_rows).items() if not g.get('review_only')}

    def shortlist(self,case,load_number,slot,browse_all=False,offset=0,limit=3):
        target='full' if slot in ('full_1','full_2') else slot
        used=assignments(case);candidates=[]
        groups=getattr(self,'groups',{})
        for record in self.records:
            path=record['path'];row=self.rows.get(path,{});digest=row.get('sha256')
            dismissed=case.get('template_photo_dismissals',{}).get(f'{load_number}:{slot}',{}).get(path,{})
            if digest and dismissed.get('sha256')==digest:continue
            financial=any(d.get('confirmed') and d.get('path')==path and d.get('role') in DOCUMENT_ROLES for d in case.get('package_documents',[]))
            if financial and not browse_all:continue
            places=[(n,s) for n,s,p in used if p==path or (digest and self.rows.get(p,{}).get('sha256')==digest)]
            tag=case.get('photo_load_assignments',{}).get(path,{})
            manual_load=tag.get('load') if digest and tag.get('sha256')==digest else None
            share_candidate=bool(browse_all and slot in ('height','width','length') and all(s==slot for n,s in places if n!=load_number))
            if (any(n!=load_number for n,s in places) or (manual_load and manual_load!=load_number)) and not share_candidate:continue
            if not browse_all and any(s!=slot and s in CORE for n,s in places):continue
            text=self.text.get(path,{});vendor_text_load=text.get('load');group=groups.get(path,{})
            if group.get('status')=='card_mapping_conflict' and not browse_all:continue
            # Vendor numbering is not package numbering. Only a reviewed mapping
            # may make a text number a load-specific filter or ranking bonus.
            text_load=group.get('load') if group.get('vendor_load')==vendor_text_load else None
            if not browse_all and text_load and text_load!=load_number and manual_load!=load_number:continue
            if not browse_all and group.get('load') not in (None,load_number) and manual_load!=load_number:continue
            scores=self.scores.get(path,{});score=scores.get(target,0)
            claim=getattr(self,'card_claims',{}).get(path)
            card_stage=claim.get('stage') if claim else None
            stage_conflict=bool(target in ('empty','quarter','half','three_quarters','full') and card_stage and card_stage!=target)
            if stage_conflict and not browse_all:continue
            visual=bool(score>=.15 and score>scores.get('other',0) and target in sorted(scores,key=scores.get,reverse=True)[:3])
            direct=bool(text.get('slot')==slot and slot!='calculator')
            semantic=self.semantics.get(path,{})
            card_direct=bool(claim and claim.get('scene_context') and card_stage==target and (group.get('load')==load_number or manual_load==load_number) and (max(semantic.get('loaded_container',0),semantic.get('empty_container',0))>.25 or sum(scores.get(k,0) for k in ('empty','quarter','half','three_quarters','full'))>.45))
            direct=direct or card_direct
            reviewed=case.get('photo_category_examples',{}).get(path,{})
            expected='measurement' if slot in ('height','width','length') else 'documents' if slot=='receipt' else 'container_photos'
            category_conflict=bool(digest and reviewed.get('sha256')==digest and reviewed.get('category')!=expected)
            from photo_semantics import measurement_relevance,likely_receipt
            semantic=self.semantics.get(path,{})
            if not browse_all and slot in ('height','width','length'):
                if measurement_relevance(semantic,self.geometry.get(path)) is False:continue
                if group.get('load')==load_number and max(self.geometry.get(path,{}).get('horizontal',0),self.geometry.get(path,{}).get('vertical',0))>.20:visual=True
                if manual_load==load_number and max(scores.get(key,0) for key in ('height','width','length'))>=.10:visual=True
            if not browse_all and slot=='receipt' and semantic:
                if not likely_receipt(semantic,path,None if direct else scores):continue
                visual=True
            group_fallback=False
            if not browse_all and target in ('empty','quarter','half','three_quarters','full') and group.get('load')==load_number:
                fill=sum(scores.get(k,0) for k in ('empty','quarter','half','three_quarters','full'))
                if fill>=.35 and fill>scores.get('other',0)*1.1:
                    group_fallback=not visual;visual=True
            if not browse_all and (category_conflict or not (visual or direct)):continue
            try:
                quality=float(row.get('features',{}).get('quality',0))/10
                quality=max(0,min(1,quality)) if math.isfinite(quality) else 0
            except (ValueError,TypeError):quality=0
            rank=(2 if direct else 0)+score+.025*quality+(.85 if manual_load==load_number else .03 if text_load==load_number else 0)
            from load_identity import current_clue
            clue=current_clue(case,path,digest)
            if clue and clue.get('status')=='corroborated' and clue.get('load')==load_number:rank+=.15
            group=groups.get(path,{})
            if group.get('load')==load_number:rank+=.75
            if slot in ('height','width','length'):
                axis='vertical' if slot=='height' else 'horizontal'
                rank+=.20*self.geometry.get(path,{}).get(axis,0)
                if semantic:rank+=2*(semantic['container_measurement']-semantic['irrelevant_measurement'])
            if target in ('quarter','half','three_quarters','full') and semantic:
                # A transfer-station scene is supporting evidence, not a fill level.
                difference=semantic.get('disposal_scene',0)-semantic.get('loading_scene',0)
                rank-=min(.35,8*max(0,difference-.005))
            clue=f'Reviewed Load {manual_load}' if manual_load else f'Photo Text: Load {text_load}' if text_load else 'Load Not Confirmed'
            if group.get('load')==load_number and not manual_load:clue='Near Reviewed Card · Check Load '+str(load_number)
            candidates.append(dict(path=path,name=record.get('name',Path(path).name),sha256=digest,
                                   rank=rank,basis='Check Loading Stage' if group.get('vendor_load') and not card_stage else 'Card Stage Evidence' if card_direct else 'Photo Text Suggestion' if direct else 'Check Loading Stage' if group_fallback else 'Visual Candidate' if visual else 'Browse Original',
                                   load_clue=clue,text_load=text_load,card_stage_unread=bool(group.get('vendor_load') and not card_stage),card_stage=card_stage,stage_conflict=stage_conflict,reviewed_load_match=manual_load==load_number,group_load_match=group.get('load')==load_number))
        candidates.sort(key=lambda r:(not r['reviewed_load_match'],not r['group_load_match'],-r['rank'],r['path']))
        distinct=[];seen=set()
        for row in candidates:
            feature=self.rows.get(row['path'],{}).get('features',{})
            key=(feature.get('pixel_hash') if valid_features(feature) else None) or row['sha256'] or row['path']
            if key in seen:continue
            seen.add(key);distinct.append(row)
        return distinct[offset:offset+limit],len(distinct)

def dismiss_template_photo(case,load_number,slot,candidate):
    """Hide a checked source only for this load/box; never alter evidence."""
    if slot not in CORE|{'disposal_photo','first_10_proof'} or not 1<=load_number<=len(case.get('loads',[])):
        raise ValueError('Choose a load and photo box first.')
    path=candidate['path']
    if path not in {r['path'] for r in case.get('imported_files',[])}:raise ValueError('Import the source photo first.')
    if assigned_path(case['loads'][load_number-1],slot)==path:raise ValueError('This photo is already selected. Choose its replacement before dismissing it.')
    digest=file_digest(path)
    if not candidate.get('sha256') or candidate['sha256']!=digest:raise ValueError('This photo changed. Refresh the suggestions and inspect it again.')
    with Image.open(path) as image:image.verify()
    case.setdefault('template_photo_dismissals',{}).setdefault(f'{load_number}:{slot}',{})[path]=dict(
        sha256=digest,dismissed_at=datetime.now(timezone.utc).isoformat())

def assign_template_photo(case,load_number,slot,candidate,shared_container_confirmed=False):
    if slot not in CORE|{'disposal_photo','first_10_proof'}:raise ValueError('Use Attach Calculation for a calculation screenshot.')
    if not 1<=load_number<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
    from load_requirements import applicable
    if not applicable(case['loads'][load_number-1],slot):raise ValueError('This stage is above the confirmed final fill. Correct Final Fill in the container details before assigning it.')
    path=candidate['path']
    if path not in {r['path'] for r in case.get('imported_files',[])}:raise ValueError('Import the source photo first.')
    if any(d.get('confirmed') and d.get('path')==path and d.get('role') in DOCUMENT_ROLES for d in case.get('package_documents',[])):
        raise ValueError('This file is already a reviewed package document. Choose the actual evidence photo, or correct its document purpose first.')
    digest=file_digest(path)
    if not candidate.get('sha256') or digest!=candidate['sha256']:raise ValueError('This photo changed. Refresh the suggestions and inspect it again.')
    with Image.open(path) as image:image.verify()
    tag=case.get('photo_load_assignments',{}).get(path,{})
    shared=bool(shared_container_confirmed and slot in ('height','width','length'))
    from card_evidence import reviewed_card_mapping
    mapped=reviewed_card_mapping(case,path)
    if mapped is not None and mapped!=load_number and not shared:raise ValueError('This card is mapped to another package load. Correct its load-card mapping before placing this photo.')
    if tag.get('sha256')==digest and tag.get('load') not in (None,load_number) and not shared:raise ValueError('This photo belongs to another reviewed load. Correct that load assignment first.')
    for n,other_slot,other_path in assignments(case):
        if other_path==path:identical=True
        else:
            try:identical=file_digest(other_path)==digest
            except OSError:identical=False
        if identical and n!=load_number and not (shared and other_slot==slot):raise ValueError('This source is already assigned to another load. Check the original load evidence.')
        if n==load_number and {slot,other_slot}=={'full_1','full_2'} and not identical:
            try:identical=pixel_digest(path)==pixel_digest(other_path)
            except OSError:pass
        loading={'empty','quarter','half','three_quarters','full_1','full_2'}
        if slot in loading and other_slot in loading and not identical:
            try:identical=pixel_digest(path)==pixel_digest(other_path)
            except (OSError,ValueError):pass
        if identical and slot in loading and other_slot in loading and (n!=load_number or slot!=other_slot):
            if {slot,other_slot}!={'full_1','full_2'}:raise ValueError('Choose separate photographs for different loading stages and loads.')
        if identical and {slot,other_slot}=={'full_1','full_2'}:raise ValueError('Choose a different photograph for the second full-container view.')
    load=case['loads'][load_number-1];previous=assigned_path(load,slot)
    if slot=='disposal_photo':load[slot]=path
    elif slot=='first_10_proof':load['evidence_first_10_cyd']=path
    else:load.setdefault('photos',{})[slot]=path
    if not shared:case.get('shared_container_measurements',{}).pop(f'{load_number}:{slot}',None)
    if shared:
        case.setdefault('shared_container_measurements',{})[f'{load_number}:{slot}']=dict(path=path,sha256=digest,load=load_number,slot=slot,container_match_confirmed=True)
    if previous!=path and slot in ('height','width','length'):load['measurements_confirmed']=False
    case.setdefault('template_photo_reviews',{})[f'{load_number}:{slot}']=dict(path=path,sha256=digest,load=load_number,slot=slot,
        selected_at=datetime.now(timezone.utc).isoformat(),basis='Selected by the user in template photo review.')

class TemplateReviewWindow:
    PAGE_SIZE=2
    def review_loading_sequence(self):
        if self.index is None:self.status.configure(text='Preparing photo suggestions. Please wait.');return
        window=getattr(self,'sequence_window',None)
        if window and not window.closed:window.win.lift();return
        from loading_sequence import LoadingSequenceWindow
        self.sequence_window=LoadingSequenceWindow(self)

    def __init__(self,app):
        self.app=app;self.case=app.case;self.index=None;self.page=0;self.images=[];self.closed=False;self.results=queue.Queue();self.poll_job=None;self.resize_job=None
        self.win=tk.Toplevel(app.root);self.win.title('Review Suggested Photos')
        ttk.Style(self.win).configure('PhotoAction.TButton',padding=(4,3))
        self.win.geometry(f'{max(900,min(1100,app.root.winfo_screenwidth()-40))}x{max(600,min(800,app.root.winfo_screenheight()-80))}');self.win.minsize(900,600);self.win.transient(app.root);fit_window(self.win,app.root,(1100,800),(900,600))
        body=ttk.Frame(self.win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Fill the Template',font=(app.ui_font,20,'bold')).pack(anchor='w')
        ttk.Label(body,text='1. Choose the load and a box on the left.  2. Check the suggested photos.  3. Select Use This Photo to save and continue.',wraplength=850).pack(anchor='w',pady=(5,12))
        controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,12));ttk.Label(controls,text='Load').pack(side='left')
        self.load=tk.IntVar(value=int(app.e_load.get()));combo=ttk.Combobox(controls,textvariable=self.load,values=list(range(1,len(self.case['loads'])+1)),state='readonly',width=6);self.load_box=combo;combo.pack(side='left',padx=8)
        combo.bind('<<ComboboxSelected>>',lambda event:self.change_load())
        ttk.Button(controls,text='+ Add Load',command=self.add_load).pack(side='left',padx=(0,8))
        ttk.Button(controls,text='Review Loading Sequence',command=self.review_loading_sequence).pack(side='left')
        self.browse=tk.BooleanVar(value=False)
        more=ttk.Menubutton(controls,text='More');menu=tk.Menu(more,tearoff=False);more.configure(menu=menu);more.pack(side='right')
        menu.add_checkbutton(label='Browse All Originals',variable=self.browse,command=self.reset_page)
        menu.add_command(label='Restore Dismissed Photos',command=self.restore_dismissed)
        foot=ttk.Frame(body);foot.pack(side='bottom',fill='x',pady=(12,0))
        self.status=ttk.Label(foot,text='Preparing suggestions...',wraplength=760);self.status.pack(side='left')
        ttk.Button(foot,text='Next: Review Costs',style='Primary.TButton',command=self.finish_template).pack(side='right')
        ttk.Button(foot,text='Photo Groups',command=self.back_to_groups).pack(side='right',padx=8)
        self.status.configure(wraplength=450)
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
        current=ttk.Frame(right);self.current_frame=current;current.pack(fill='x',pady=(8,10))
        self.current=ttk.Label(current,text='',wraplength=470);self.current.pack(side='left')
        ttk.Button(current,text='Open Selected Photo',command=self.open_current).pack(side='right')
        self.cards=ttk.Frame(right)
        paging=ttk.Frame(right);self.paging=paging;paging.pack(side='bottom',fill='x',pady=(10,0));ttk.Button(paging,text='Previous Photos',command=lambda:self.move(-1)).pack(side='left')
        self.page_label=ttk.Label(paging,text='');self.page_label.pack(side='left',padx=10)
        ttk.Button(paging,text='Next Photos',command=lambda:self.move(1)).pack(side='right')
        self.cards.pack(fill='both',expand=True)
        self.win.protocol('WM_DELETE_WINDOW',self.close);self.refresh_tree();self.refresh()
        def resize(event):
            if event.widget is not self.win or self.closed:return
            if self.resize_job:self.win.after_cancel(self.resize_job)
            self.resize_job=self.win.after(120,self.render)
        self.win.bind('<Configure>',resize)
        self.win.bind('<Destroy>',lambda event:self.cleanup() if event.widget is self.win else None)
        self.update_binding=app.root.bind('<<PhotoGroupsUpdated>>',lambda event:self.automatic_update(),add='+')

    def automatic_update(self):
        if self.closed:return
        self.load_box.configure(values=list(range(1,len(self.case['loads'])+1)))
        if self.poll_job:self.needs_update=True
        else:self.refresh(background=True)
    def back_to_groups(self):self.close();self.app.organize_photos()
    def finish_template(self):
        current=self.app.case is self.case;self.close()
        if current:self.app.go(2)

    def slot(self):return self.tree.selection()[0] if self.tree.selection() else 'height'
    def refresh_tree(self,select=None):
        previous=select or self.slot();self.tree.delete(*self.tree.get_children())
        load=self.case['loads'][self.load.get()-1]
        for key,label in SLOTS:
            from load_requirements import applicable,stage_label
            label=stage_label(load,key,label)
            path=assigned_path(load,key);status='Selected' if path and Path(path).is_file() else 'Missing' if applicable(load,key) else 'Not Required'
            self.tree.insert('','end',iid=key,text=label,values=(status,))
        from load_requirements import applicable
        required=[key for key,_ in SLOTS if applicable(load,key)]
        selected=sum(bool(assigned_path(load,key) and Path(assigned_path(load,key)).is_file()) for key in required)
        self.progress.configure(text=f'{selected} of {len(required)} required boxes selected')
        self.tree.selection_set(previous);self.tree.see(previous)
    def change_load(self):self.app.e_load.set(str(self.load.get()));self.refresh_tree();self.reset_page()
    def add_load(self):
        if self.app.case is not self.case:self.close();return
        self.app.add_load();self.app.save();self.load.set(len(self.case['loads']));self.app.e_load.set(str(self.load.get()));self.refresh()
    def refresh(self,background=False):
        if self.closed or self.app.case is not self.case:return
        self.status.configure(text='Preparing suggestions locally...')
        if not background:self.index=None
        self.load_box.configure(values=list(range(1,len(self.case['loads'])+1)))
        if not background:self.refresh_tree()
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
        first=self.index is None;self.index=index
        for path,entry in index.geometry.items():
            row=self.case.get('local_photo_results',{}).get(path,{})
            if row.get('sha256')==entry['sha256']:self.case.setdefault('template_geometry_cache',{})[path]=entry
        # Background results become available for the next action without moving
        # a photo or button while somebody is inspecting the current choices.
        if first:self.reset_page()
        else:self.status.configure(text='Suggestions updated in the background. Your current choices stay in place until you continue.')
        if getattr(self,'needs_update',False):self.needs_update=False;self.refresh(background=True)
    def reset_page(self):self.page=0;self.render()
    def move(self,amount):self.page=max(0,self.page+amount);self.render()
    def dismiss(self,candidate):
        if self.closed or self.app.case is not self.case:return
        try:
            dismiss_template_photo(self.case,self.load.get(),self.slot(),candidate)
            self.app.save();self.render()
        except Exception as exc:messagebox.showwarning('Photo Not Dismissed',str(exc),parent=self.win)
    def restore_dismissed(self):
        if self.closed or self.app.case is not self.case:return
        self.case.get('template_photo_dismissals',{}).pop(f'{self.load.get()}:{self.slot()}',None)
        self.app.save();self.reset_page()
    def open_current(self):
        from photo_inspector import inspect_photos
        inspect_photos(self.win,[assigned_path(self.case['loads'][self.load.get()-1],self.slot())])
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
        old_size=self.PAGE_SIZE;self.PAGE_SIZE=1 if self.win.winfo_width()<980 else 2
        if old_size!=self.PAGE_SIZE:self.page=(self.page*old_size)//self.PAGE_SIZE
        for child in self.cards.winfo_children():child.destroy()
        for column in range(2):self.cards.columnconfigure(column,weight=0,uniform='')
        self.images=[];slot=self.slot();n=self.load.get();label=dict(SLOTS)[slot]
        from load_requirements import stage_label
        label=stage_label(self.case['loads'][n-1],slot,label)
        self.heading.configure(text=f'Load {n} · {label}')
        self.box_help.configure(text=BOX_HELP.get(slot,''),wraplength=max(350,self.cards.winfo_width()-10))
        selected=assigned_path(self.case['loads'][n-1],slot)
        self.current.configure(text='Selected: '+Path(selected).name if selected else '')
        if selected:
            if not self.current_frame.winfo_manager():self.current_frame.pack(fill='x',pady=(8,10),before=self.cards)
        else:self.current_frame.pack_forget()
        if slot=='calculator':
            self.paging.pack_forget()
            ttk.Label(self.cards,text='Attach the actual cubic yard calculation after confirming this load’s measurements.',wraplength=500).pack(anchor='w',pady=15)
            ttk.Button(self.cards,text='Container Details',command=self.container_details).pack(anchor='w',pady=(0,10))
            ttk.Button(self.cards,text='Attach Calculation',command=lambda:self.app.attach_calculator(n-1)).pack(anchor='w');return
        if not self.paging.winfo_manager():self.paging.pack(side='bottom',fill='x',pady=(10,0),before=self.cards)
        if self.index is None:return
        candidates,total=self.index.shortlist(self.case,n,slot,self.browse.get(),self.page*self.PAGE_SIZE,self.PAGE_SIZE)
        service=getattr(self.app,'_background_photos',None)
        if service and service.case is self.case:service.prioritize(c['path'] for c in candidates)
        if self.page and not candidates:self.page=max(0,(total-1)//self.PAGE_SIZE);return self.render()
        self.page_label.configure(text=f'{self.page+1} / {max(1,(total+self.PAGE_SIZE-1)//self.PAGE_SIZE)}')
        self.status.configure(text='Check the photo and its load, then choose Use This Photo. You can return to missing boxes later.')
        if not candidates:
            ttk.Label(self.cards,text='No matching suggestions yet. Photos are organized in the background. Use More → Browse All Originals to choose from your files.',wraplength=500).pack(anchor='w',pady=20);return
        self.displayed_candidates=candidates
        compare=candidates
        if self.PAGE_SIZE==1:compare=self.index.shortlist(self.case,n,slot,self.browse.get(),self.page,2)[0]
        if len(compare)==2:
            ttk.Button(self.cards,text='Compare These Photos',command=lambda:self.compare_candidates(compare)).grid(row=1,column=0,columnspan=self.PAGE_SIZE,pady=6)
        for column,candidate in enumerate(candidates):
            preview_width=max(140,min(500 if self.PAGE_SIZE==1 else 300,(self.cards.winfo_width()-30)//self.PAGE_SIZE-20))
            preview_height=max(65,min(300,self.cards.winfo_height()-(125 if self.PAGE_SIZE==1 else 190)))
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
            if self.cards.winfo_height()>=330:
                ttk.Label(card,text=display_name,wraplength=preview_width,style='Card.TLabel').pack(anchor='w',pady=5)
            from visual_photo_review import timing_clues
            text=self.case.get('photo_text_cache',{}).get(candidate['path'],{})
            timing=timing_clues(candidate['path'],text.get('text','') if text.get('sha256')==candidate['sha256'] else '')
            if timing['clues']:
                label='Date / Time Needs Review' if timing['flags'] else next((c['date']+(' '+c['time'] if c.get('time') else ' · Date Only') for c in timing['clues'] if c.get('date')),'Date Needs Review')
                ttk.Label(card,text=label,wraplength=preview_width,style='Card.TLabel').pack(anchor='w',pady=3)
            ttk.Label(actions,text=candidate['basis']+' · '+candidate['load_clue'],wraplength=preview_width,style='Card.TLabel').pack(anchor='w',pady=(0,4))
            buttons=ttk.Frame(actions,style='Card.TFrame');buttons.pack(fill='x')
            if self.PAGE_SIZE==1:
                ttk.Button(buttons,text='Open Full Photo',style='PhotoAction.TButton',command=lambda p=candidate['path']:self.compare_candidates([{'path':p}])).pack(side='left',padx=(0,5))
                ttk.Button(buttons,text='Use This Photo',style='Primary.TButton',state='normal' if ready else 'disabled',command=lambda c=candidate:self.use(c)).pack(side='left',padx=5)
                ttk.Button(buttons,text='Not a Match',style='PhotoAction.TButton',state='normal' if ready else 'disabled',command=lambda c=candidate:self.dismiss(c)).pack(side='left',padx=5)
            else:
                ttk.Button(buttons,text='Use This Photo',style='Primary.TButton',state='normal' if ready else 'disabled',command=lambda c=candidate:self.use(c)).pack(fill='x',pady=3)
                row=ttk.Frame(buttons,style='Card.TFrame');row.pack(fill='x')
                ttk.Button(row,text='Open Full Photo',style='PhotoAction.TButton',command=lambda p=candidate['path']:self.compare_candidates([{'path':p}])).pack(side='left')
                ttk.Button(row,text='Not a Match',style='PhotoAction.TButton',state='normal' if ready else 'disabled',command=lambda c=candidate:self.dismiss(c)).pack(side='right')
            if slot in ('height','width','length'):
                other=ttk.Menubutton(actions,text='Use for Another Dimension');options=tk.Menu(other,tearoff=False);other.configure(menu=options);other.pack(fill='x',pady=3)
                for dimension,title in [('height','Height'),('width','Width'),('length','Length')]:options.add_command(label=title,command=lambda d=dimension,c=candidate:self.use_dimension(c,d))
    def use_dimension(self,candidate,dimension):
        self.refresh_tree(dimension);self.use(candidate)
    def compare_candidates(self,candidates):
        from photo_inspector import inspect_photos
        inspect_photos(self.win,[c['path'] for c in candidates])
    def use(self,candidate):
        if self.app.case is not self.case:self.close();return
        n=self.load.get();slot=self.slot()
        reviewed=self.case.get('photo_load_assignments',{}).get(candidate['path'],{})
        corrected=reviewed.get('sha256')==candidate.get('sha256') and reviewed.get('load')==n
        if not corrected and candidate.get('text_load') not in (None,n) and not messagebox.askyesno('Check Load Number',f'Photo text suggests Load {candidate["text_load"]}. Have you checked that it belongs in Load {n}?',parent=self.win):return
        old=assigned_path(self.case['loads'][n-1],slot)
        if old and old!=candidate['path'] and not messagebox.askyesno('Replace Selected Photo',f'Replace the selected {dict(SLOTS)[slot].lower()} photo for Load {n}?',parent=self.win):return
        shared=False
        if slot in ('height','width','length'):
            digest=candidate.get('sha256')
            others=[]
            for other_number,other_slot,other_path in assignments(self.case):
                if other_number==n:continue
                try:identical=other_path==candidate['path'] or file_digest(other_path)==digest
                except OSError:identical=False
                if identical:others.append((other_number,other_slot))
            tag=self.case.get('photo_load_assignments',{}).get(candidate['path'],{})
            tag_load=tag.get('load') if tag.get('sha256')==digest else None
            if others or tag_load not in (None,n):
                if any(other_slot!=slot for _,other_slot in others):
                    messagebox.showwarning('Choose Different Evidence','This photo is used for a different purpose on another load. Choose the appropriate measurement photo.',parent=self.win);return
                shared=messagebox.askyesno('Confirm the Same Container','This measurement photo is already associated with another load. Have you checked that both loads used the same container with the same '+dict(SLOTS)[slot].lower()+'? Only the photo will be reused; confirm this load’s dimensions separately.',parent=self.win)
                if not shared:return
        try:
            assign_template_photo(self.case,n,slot,candidate,shared_container_confirmed=shared);self.app.save();self.app.refresh_assignments()
            keys=[key for key,_ in SLOTS];following=keys[keys.index(slot)+1:]+keys[:keys.index(slot)]
            from load_requirements import applicable
            next_slot=next((key for key in following if key!='calculator' and applicable(self.case['loads'][n-1],key) and not assigned_path(self.case['loads'][n-1],key)),slot)
            self.browse.set(False);self.refresh_tree(next_slot);self.reset_page()
        except Exception as exc:messagebox.showwarning('Photo Not Assigned',str(exc),parent=self.win)
    def close(self):
        if self.closed:return
        self.cleanup();self.win.destroy()
        refresh=getattr(self.app,'refresh_load_progress',None)
        if refresh and self.app.case is self.case:refresh()
    def cleanup(self):
        self.closed=True
        if getattr(self,'update_binding',None):
            self.app.root.unbind('<<PhotoGroupsUpdated>>',self.update_binding);self.update_binding=None
        for job in (self.poll_job,self.resize_job):
            if job:
                try:self.win.after_cancel(job)
                except tk.TclError:pass
        self.poll_job=self.resize_job=None
