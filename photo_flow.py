from ui_windows import fit_window
"""Batch photo organization with background local analysis and explicit evidence choices."""
import copy
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageOps,ImageTk
from calculator_evidence import file_digest
from review_assist import checked_rows,category_matches,confirm_load_membership,decode_embedding
from visual_photo_review import timing_clues,current_stage,apply_visual_stage,STAGES,PHASE
from local_photo_sorter import MODEL_DIGEST,MODEL_ID,VERSION,RUNTIME,batch,SetupCancelled

IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
CATEGORIES={'all':'All Photos','unreviewed':'Not Organized','measurement':'Measurements','container_photos':'Containers & Loads','property_photos':'Property & Debris','stage:during':'During Suggestions','stage:before':'Before Suggestions','stage:after':'After Suggestions','documents':'Documents & Receipts','other':'Other / Unclear'}

def build_photo_rows(case,previous=None):
    records=[r for r in case.get('imported_files',[]) if Path(r['path']).suffix.lower() in IMAGE_EXT]
    cache=dict(case.get('local_photo_results',{}))
    for path,entry in case.get('photo_text_cache',{}).items():
        if path not in cache:cache[path]={'sha256':entry.get('sha256')}
    old={r['path']:r for r in previous or []};rows={};stats={}
    for record in records:
        path=record['path'];entry=cache.get(path,{})
        try:
            source=Path(path).stat();stats[path]=(source.st_size,source.st_mtime_ns,entry.get('sha256'),entry.get('prompt_version'),entry.get('prediction',{}).get('category'),bool(entry.get('prediction',{}).get('embedding')))
            if old.get(path,{}).get('_source_state')==stats[path]:rows[path]=old[path]['_checked_row']
            else:
                current=checked_rows([record],cache,MODEL_DIGEST,VERSION).get(path,{})
                rows[path]=current or {'sha256':file_digest(path)}
        except OSError:continue
    categories=category_matches(records,rows,case);out=[]
    for position,record in enumerate(records):
        path=record['path'];row=rows.get(path,{})
        try:digest=row.get('sha256') or file_digest(path)
        except OSError:continue
        text=case.get('photo_text_cache',{}).get(path,{})
        info=timing_clues(path,(text.get('text','')+'\n'+text.get('timing_text','')) if text.get('sha256')==digest else '')
        clues=info['clues'];dates={c['date'] for c in clues if c.get('date')};times={c['time'] for c in clues if c.get('time')}
        date=next(iter(dates)) if len(dates)==1 and not info['flags'] else None
        from load_identity import explicit_clock
        clock=next(iter(times)) if date and len(times)==1 and all(explicit_clock(c) for c in clues if c.get('time')) else None
        timing=f'{date} {clock}' if clock else f'{date} · Time Needs Review' if date and times else f'{date} · Date Only' if date else 'Conflicting Dates' if info['flags'] else 'Date Not Available'
        category=categories[path]['category']
        if category in ('invoice','bid','estimate','dump_receipt'):category='documents'
        if category not in CATEGORIES:category='other'
        tag=case.get('photo_load_assignments',{}).get(path,{})
        load=tag.get('load') if tag.get('sha256')==digest else None
        card=case.get('load_card_reviews',{}).get(path,{})
        if not load and card.get('confirmed') and card.get('sha256')==digest:load=card.get('load')
        if not load:
            loads=[i for i,l in enumerate(case.get('loads',[]),1) if path in list(l.get('photos',{}).values())+[l.get('disposal_photo'),l.get('evidence_first_10_cyd')]]
            if len(loads)==1:load=loads[0]
        from photo_locations import photo_locations
        locations=photo_locations(case,path,digest)
        stage=current_stage(case,path)
        out.append(dict(record,path=path,sha256=digest,category=category,load=load,stage=stage,timing=timing,location_clues=locations,
                        sequence_date=date,sequence_time=date+'T'+clock if date and clock else None,
                        sequence_source='camera' if date and clock and any(c['source']=='Camera Metadata' and c.get('date')==date and c.get('time')==clock for c in clues) else 'photo_text' if date and clock else None,
                        sort_key=(date or '9999',clock or '',position),position=position,embedding=decode_embedding(row),
                        _source_state=stats.get(path),_checked_row=row))
    from load_identity import propose_loads
    proposals=propose_loads(case,out)
    from load_groups import propose_groups
    from photo_semantics import scores as semantic_scores,stage_suggestion
    groups=propose_groups(dict(case,local_photo_results=rows),out)
    from evidence_groups import propose_date_review_groups
    groups=dict(propose_date_review_groups(case,out,groups),**groups)
    from reviewed_stage_examples import suggest_stages
    learned=suggest_stages(case,out)
    for row in out:
        direct=proposals.get(row['path'],{});group=groups.get(row['path'],{})
        row['proposal']=direct if direct.get('status')=='conflict' and not group.get('card_number_reviewed') else dict(direct,**group) if group else direct
        row['stage_proposal']=stage_suggestion(semantic_scores(rows.get(row['path'],{})),row['category'],rows.get(row['path'],{})) if row['stage']=='review' else None
        example=learned.get(row['path'])
        if example:
            existing=row['stage_proposal']
            row['stage_proposal']=example if not existing or existing['stage']==example['stage'] else None
    from trip_bounds import review_windows
    windows=review_windows(case,out)
    for row in out:
        if not row.get("proposal"):row["proposal"]=windows.get(row["path"],{})
    from related_review import related_groups
    related=related_groups(case,out)
    for row in out:row['review_group']=related.get(row['path'],{})
    return out,rows

class BackgroundPhotoWork:
    """One vision worker and bounded OCR batches, owned by the current case."""
    def __init__(self,app):
        self.app=app;self.case=app.case;self.directory=Path(app.case_dir);self.cancel=threading.Event();self.events=queue.Queue()
        self._vision_running=True;self.reader_running=False;self.load_attempted=set();self.load_failure=False
        self.closed=False;self.status='Preparing photo organization...';self.job=None;self.text_attempted=set();self.priority=[];self.changed=False;self.last_signal=0
        records=[dict(r) for r in self.case.get('imported_files',[]) if Path(r['path']).suffix.lower() in IMAGE_EXT]
        self.record_paths={r['path'] for r in records}
        def work():
            try:
                if not RUNTIME.ready():
                    RUNTIME.setup(self.cancel,lambda message,done,total:self.events.put(('status',message)))
                if self.cancel.is_set():return
                def photo_ready(path,row,done,total,*rest):
                    from card_regions import locate_cards,VERSION as CARD_DETECTOR_VERSION
                    if not self.cancel.is_set():
                        try:
                            from load_identity import card_candidate
                            regions=locate_cards(path);row.update(card_regions=regions,card_detected=bool(regions) or card_candidate(path,''),card_detector_version=CARD_DETECTOR_VERSION)
                        except (OSError,ValueError):pass
                    self.events.put(('photo',(path,row,done,total)))
                result=batch(records,dict(name=MODEL_ID,digest=MODEL_DIGEST),self.directory/'local_photo_sorting.json',self.cancel,
                    photo_ready)
                self.events.put(('status','Photo groups are ready.' if not result['cancelled'] else 'Photo organization paused.'))
            except Exception as exc:self.events.put(('status','Automatic sorting unavailable. You can organize photos manually. '+str(exc)[:140]))
            finally:self._vision_running=False;self.events.put(('finished',None))
        threading.Thread(target=work,daemon=True).start();self.poll()
    @property
    def running(self):return self._vision_running or self.reader_running
    def notify(self):
        if self.changed and time.monotonic()-self.last_signal>=2:
            self.app.status.set(self.status)
            self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail');self.changed=False;self.last_signal=time.monotonic()
    def prioritize(self,paths):self.priority=list(dict.fromkeys(list(paths)+self.priority))[:12]
    def poll(self):
        if self.closed:return
        if self.app.case is not self.case:self.close();return
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='photo':
                path,row,done,total=value;self.case.setdefault('local_photo_results',{})[path]=row
                self.status=f'Organizing Photos · {done} of {total}';self.changed=True
            elif kind=='status':self.status=value;self.changed=True
            elif kind=='finished':self._vision_running=False;self.changed=True;self.app.save()
            elif kind=='load_result':
                path,entry=value;self.case.setdefault('load_identity_cache',{})[path]=entry;self.changed=True;self.app.save()
            elif kind=='load_status':self.status=value;self.changed=True
            elif kind=='load_retryable':self.load_attempted.difference_update(value)
        self.notify()
        if not self.cancel.is_set() and not self.app.scan_running:
            todo=[]
            records=self.case.get('imported_files',[]);by_path={r['path']:r for r in records}
            ordered=[by_path[p] for p in self.priority if p in by_path]+records
            for record in ordered:
                path=record['path']
                if Path(path).suffix.lower() not in IMAGE_EXT:continue
                entry=self.case.get('photo_text_cache',{}).get(path,{})
                source=self.case.get('local_photo_results',{}).get(path,{})
                timing_ready=bool(source.get('card_detected') or source.get('card_regions') or source.get('prediction',{}).get('category') in ('container_photos','measurement'))
                attempt=(path,source.get('sha256'),timing_ready)
                if attempt in self.text_attempted:continue
                try:fresh=entry.get('sha256')==file_digest(path)
                except OSError:continue
                self.text_attempted.add(attempt)
                if not fresh or (timing_ready and 'timing_text' not in entry):todo.append(record)
                if len(todo)==3:break
            if todo:
                self.app.scan_photos(todo,on_complete=lambda:self.text_done(),background=True)
        self.read_loads()
        self.job=self.app.root.after(300,self.poll)
    def read_loads(self):
        if self.cancel.is_set() or self.reader_running or self.load_failure:return
        from load_identity import current_clue
        records=self.case.get('imported_files',[]);by_path={r['path']:r for r in records}
        from photo_semantics import scores as semantic_scores
        def priority(record):
            source=self.case.get('local_photo_results',{}).get(record['path'],{});values=semantic_scores(source)
            return (record['path'] not in self.priority,not bool(source.get('card_detected') or source.get('card_regions')),-(values.get('load_board',0)-values.get('property',0)),record['path'])
        ordered=sorted(records,key=priority);todo=[]
        for record in ordered:
            path=record['path'];entry=self.case.get('photo_text_cache',{}).get(path,{})
            source=self.case.get('local_photo_results',{}).get(path,{})
            sha=entry.get('sha256') or (source.get('sha256') if source.get('card_detected') or source.get('card_regions') else None)
            text=entry.get('text','') if entry.get('sha256')==sha else ''
            import hashlib
            key=(path,sha,hashlib.sha256(text.encode()).hexdigest())
            if Path(path).suffix.lower() not in IMAGE_EXT or not key[1] or key in self.load_attempted:continue
            self.load_attempted.add(key)
            existing=current_clue(self.case,path,key[1])
            from load_identity import text_numbers
            if not existing or text_numbers(text):todo.append((path,key[1],text))
            if len(todo)==3:break
        if not todo:return
        self.reader_running=True
        def work():
            from load_identity import card_candidate,read_load_card
            from load_text_runtime import RUNTIME as reader
            try:
                for position,(path,sha,text) in enumerate(todo):
                    if self.cancel.is_set():break
                    try:
                        if file_digest(path)!=sha:continue
                        from photo_semantics import scores as semantic_scores
                        source=self.case.get('local_photo_results',{}).get(path,{})
                        scene=semantic_scores(source) if source.get('sha256')==sha else None
                        if not card_candidate(path,text,scene_scores=scene):continue
                        if not reader.ready():reader.setup(self.cancel,lambda msg,done,total:self.events.put(('load_status',f'{msg} · {done/1e6:.0f} / {total/1e6:.0f} MB')))
                        self.events.put(('load_status','Checking Load Cards Locally...'))
                        result=read_load_card(path,text,self.cancel,reader);self.events.put(('load_result',(path,result)))
                    except SetupCancelled:break
                    except Exception as exc:
                        self.load_failure=True
                        self.events.put(('load_retryable',[(p,d,hashlib.sha256(t.encode()).hexdigest()) for p,d,t in todo[position:]]))
                        self.events.put(('load_status','Load-card reading paused. Other photo review remains available. '+str(exc)[:120]));break
            finally:self.reader_running=False
        threading.Thread(target=work,daemon=True).start()
    def retry_reading(self):
        if self.closed or self.app.case is not self.case or self.reader_running or self.cancel.is_set() or not self.load_failure:return False
        # Apply queued retry keys before scheduling again; successful earlier
        # cards keep their completed attempts and source-bound results.
        retained=[]
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='load_retryable':self.load_attempted.difference_update(value)
            elif kind!='load_status':retained.append((kind,value))
        for event in retained:self.events.put(event)
        self.load_failure=False;self.status='Retrying Load-Card Reading...';self.changed=True
        return True

    def text_done(self):
        if not self.closed and self.app.case is self.case:self.changed=True
    def close(self):
        self.closed=True;self.cancel.set()
        if self.job:
            try:self.app.root.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None

class PhotoFlowWindow:
    PAGE_SIZE=6
    def __init__(self,app):
        self.app=app;self.case=app.case;self.rows=[];self.checked={};self.visible=[];self.selected=set();self.images=[];self.page=0;self.closed=False;self.loading=False;self.dirty=True;self.related=None;self.results=queue.Queue();self.job=None;self.last_action=None;self.resize_job=None
        self.win=tk.Toplevel(app.root);self.win.title('Organize Photos');self.win.geometry(f'{max(900,min(1120,app.root.winfo_screenwidth()-40))}x{max(650,min(820,app.root.winfo_screenheight()-60))}');self.win.minsize(900,650);self.win.transient(app.root);fit_window(self.win,app.root,(1120,820),(900,600))
        body=ttk.Frame(self.win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Organize Photos',font=(app.ui_font,22,'bold')).pack(anchor='w')
        ttk.Label(body,text='Choose a photo group or filter, then select photos to assign. The same container can appear in several loads.',wraplength=1000).pack(anchor='w',pady=(5,12))
        self.status=ttk.Label(body,text='Preparing photos...',style='Muted.TLabel',wraplength=1000);self.status.pack(fill='x',pady=(0,10));self.status.bind('<Configure>',lambda e:self.status.configure(wraplength=max(240,e.width)))
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(12,0))
        self.selection=ttk.Label(footer,text='0 Selected');self.selection.pack(side='left')
        self.target=tk.StringVar(value='Choose a Load or Stage');self.target_box=ttk.Combobox(footer,textvariable=self.target,state='readonly',width=22);self.target_box.pack(side='left',padx=8)
        self.apply_button=ttk.Button(footer,text='Apply to Selected',command=self.apply,style='Primary.TButton',state='disabled');self.apply_button.pack(side='left')
        self.target.trace_add('write',lambda *args:self.update_apply_state())
        ttk.Button(footer,text='Next: Fill Template',command=self.next_step,style='Primary.TButton').pack(side='right')
        self.review_help=ttk.Label(body,text='Select only photos you have checked. Matching containers can belong to different loads.',wraplength=1000,style='Muted.TLabel');self.review_help.pack(side='bottom',fill='x',pady=(8,0))
        self.target_box.bind('<<ComboboxSelected>>',lambda e:self.target_help())
        filters=ttk.Frame(body);filters.pack(fill='x',pady=(0,10))
        ttk.Label(filters,text='Photo Group / Load').pack(side='left',padx=(0,8))
        self.load_filter=tk.StringVar(value='All Loads');self.load_box=ttk.Combobox(filters,textvariable=self.load_filter,state='readonly',width=27);self.load_box.pack(side='left');self.load_box.bind('<<ComboboxSelected>>',lambda e:self.filter_load())
        self.sort=tk.StringVar(value='Photo Date');sort=ttk.Combobox(filters,textvariable=self.sort,values=['Photo Date','Import Order'],state='readonly',width=15);sort.pack(side='left',padx=8);sort.bind('<<ComboboxSelected>>',lambda e:self.reset_page())
        actions=ttk.Frame(body);actions.pack(fill='x',pady=(0,10))
        ttk.Button(filters,text='Review Load Cards',command=self.review_cards).pack(side='left',padx=(0,8))
        ttk.Button(actions,text='Select This Page',command=self.select_page).pack(side='left')
        ttk.Button(actions,text='Group This Trip',command=self.group_trip).pack(side='left',padx=4)
        self.undo_button=ttk.Button(actions,text='Undo Last Batch',command=self.undo_batch,state='disabled');self.undo_button.pack(side='left',padx=4)
        more=ttk.Menubutton(actions,text='More');menu=tk.Menu(more,tearoff=False);more.configure(menu=menu);more.pack(side='right')
        menu.add_command(label='Compare Two Selected Photos',command=self.compare_selected)
        menu.add_command(label='Find Related Views',command=self.find_related);menu.add_command(label='Show All Views',command=self.clear_related)
        types=tk.Menu(menu,tearoff=False)
        for key in ('measurement','container_photos','property_photos','documents','other'):
            types.add_command(label=CATEGORIES[key],command=lambda k=key:self.change_category(k))
        menu.add_cascade(label='Change Photo Type',menu=types)
        times=tk.Menu(menu,tearoff=False);times.add_command(label='Mark Selected Photo as Load Start',command=lambda:self.mark_boundary('start'));times.add_command(label='Mark Selected Photo as Load End',command=lambda:self.mark_boundary('end'));times.add_command(label='Clear This Load’s Time Boundaries',command=self.clear_boundaries);menu.add_cascade(label='Load Timing',menu=times)
        menu.add_command(label='Select All Filtered Photos',command=self.select_filtered)
        menu.add_command(label='Clear Selection',command=self.clear_selection);menu.add_command(label='Add Another Load',command=self.add_load)
        menu.add_command(label='Review Documents',command=lambda:(self.close(),app.go(0)))
        self.page_size=tk.StringVar(value='6')
        ttk.Label(actions,text='Photos per Page').pack(side='left',padx=(12,4))
        density=ttk.Combobox(actions,textvariable=self.page_size,values=['6','12','24'],state='readonly',width=4);density.pack(side='left');density.bind('<<ComboboxSelected>>',lambda e:self.reset_page())
        self.pager=ttk.Label(actions,text='');self.pager.pack(side='right',padx=8)
        ttk.Button(actions,text='Next',command=lambda:self.move(1)).pack(side='right');ttk.Button(actions,text='Previous',command=lambda:self.move(-1)).pack(side='right',padx=4)
        content=ttk.Frame(body);content.pack(fill='both',expand=True)
        self.category=tk.StringVar(value='all');side=ttk.Frame(content,width=170);side.pack(side='left',fill='y',padx=(0,14))
        for key,label in CATEGORIES.items():ttk.Radiobutton(side,text=label,value=key,variable=self.category,command=self.category_changed).pack(anchor='w',pady=4)
        viewport=ttk.Frame(content);viewport.pack(side='left',fill='both',expand=True)
        self.canvas=tk.Canvas(viewport,highlightthickness=0,background='#f2f5f8')
        scrollbar=ttk.Scrollbar(viewport,command=self.canvas.yview);scrollbar.pack(side='right',fill='y')
        self.canvas.pack(fill='both',expand=True);self.canvas.configure(yscrollcommand=scrollbar.set)
        self.cards=ttk.Frame(self.canvas);self.cards_window=self.canvas.create_window((0,0),window=self.cards,anchor='nw')
        self.cards.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize_grid)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units'))
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-1,'units'))
        self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(1,'units'))
        self.bind_id=app.root.bind('<<PhotoGroupsUpdated>>',lambda e:self.mark_dirty(),add='+')
        self.win.protocol('WM_DELETE_WINDOW',self.close);self.update_choices();self.poll();app.start_photo_work()
    def resize_grid(self,event):
        self.canvas.itemconfigure(self.cards_window,width=event.width)
        if self.resize_job:self.win.after_cancel(self.resize_job)
        self.resize_job=self.win.after(100,self.resized_grid)
    def resized_grid(self):
        self.resize_job=None
        if not self.closed:self.render()
    def remember_batch(self,before,paths,kind):
        from review_actions import remember,record_metric
        self.last_action=remember(self.case,before,paths,kind);record_metric(self.case,kind,len(paths));self.undo_button.configure(state='normal')
    def undo_batch(self):
        if self.app.case is not self.case:self.close();return
        from review_actions import undo
        try:
            undo(self.case,self.last_action);self.last_action=None;self.undo_button.configure(state='disabled');self.app.save();self.selected.clear();self.dirty=True
            self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
        except Exception as exc:messagebox.showwarning('Cannot Undo This Batch',str(exc),parent=self.win)
    def group_trip(self):
        if self.app.case is not self.case:self.close();return
        if len(self.selected)!=2 or not self.target.get().startswith('Load '):
            messagebox.showinfo('Choose Trip Endpoints','Select the first and last container photo of one trip, then choose its load in the bottom bar.',parent=self.win);return
        if not messagebox.askyesno('Group This Trip','Have you checked that both photos show the same physical trip and its correct first and last times? Photos between them will be grouped for review, not assigned automatically.',parent=self.win):return
        from trip_bounds import confirm_trip_bounds
        from review_actions import snapshot
        try:
            paths=sorted(self.selected);before=snapshot(self.case)
            confirm_trip_bounds(self.case,[r for r in self.rows if r['path'] in self.selected],int(self.target.get().split()[-1]))
            self.remember_batch(before,paths,'trip');self.app.save();self.selected.clear();self.dirty=True;self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
        except Exception as exc:messagebox.showwarning('Trip Needs Review',str(exc),parent=self.win)
    def category_changed(self):
        if self.category.get().startswith('stage:'):
            stage=self.category.get().split(':')[1];self.target.set(STAGES[stage]);self.target_help()
        self.reset_page()
    def review_cards(self):self.app.review_load_cards()
    def update_choices(self):
        loads=[f'Load {i}' for i in range(1,len(self.case['loads'])+1)]
        groups=list(dict.fromkeys(g['group_label'] for r in self.rows for g in (r.get('proposal',{}),r.get('review_group',{})) if g.get('group_label')))
        choices=['All Loads','Not Assigned','Load Clues to Review']+loads+['Suggested '+n for n in loads]+groups
        self.load_box.configure(values=choices);self.target_box.configure(values=loads+['Before Removal','Removal in Progress','After Removal'])
        if self.load_filter.get() not in choices:self.load_filter.set('All Loads')
    def update_apply_state(self):
        valid=self.target.get() in [f'Load {n}' for n in range(1,len(self.case['loads'])+1)]+[STAGES[s] for s in PHASE]
        self.apply_button.configure(state='normal' if valid and self.selected else 'disabled')
    def target_help(self):
        target=self.target.get();help={'Before Removal':'Before: the property and debris before removal starts. An empty container is different evidence.',
            'Removal in Progress':'During: debris removal underway at the property. Container fill levels belong in the load template.',
            'After Removal':'After: the photographed property area is clear of debris. One clear area does not establish that the entire property is clear.'}
        self.review_help.configure(text=help.get(target,f'Check that every selected photo belongs to {target}. The same container can be used for several loads.'))
    def filter_load(self):
        label=self.load_filter.get()
        is_group=any(g.get('group_label')==label for r in self.rows for g in (r.get('proposal',{}),r.get('review_group',{})))
        if label in ('All Loads','Not Assigned','Load Clues to Review') or is_group:self.target.set('Choose a Load or Stage')
        if is_group:
            self.category.set('all');self.sort.set('Photo Date')
            numbers={g.get('load') for r in self.rows for g in (r.get('proposal',{}),r.get('review_group',{})) if g.get('group_label')==label}
            if len(numbers)==1 and None not in numbers:
                self.target.set('Load '+str(next(iter(numbers))));self.target_help()
            else:self.review_help.configure(text='These photos look related. Check the trip and visible stage before applying a load or property stage. The same container may cover multiple trips.')
        if label=='Load Clues to Review' or label.startswith('Suggested Load '):self.category.set('all')
        if label.split()[-1].isdigit() and (label.startswith('Load ') or label.startswith('Suggested Load ')):
            self.target.set('Load '+label.split()[-1]);self.target_help()
        self.reset_page()
    def mark_dirty(self):self.dirty=True
    def poll(self):
        if self.closed:return
        if self.app.case is not self.case:self.close();return
        service=getattr(self.app,'_background_photos',None)
        if service and service.case is self.case:self.status.configure(text=service.status+(' · Reading photo text in the background.' if self.app.scan_running else ''))
        if self.dirty and not self.loading:
            self.loading=True;self.dirty=False;snapshot=copy.deepcopy(self.case);previous=list(self.rows)
            def build():
                try:self.results.put((build_photo_rows(snapshot,previous),None))
                except Exception as exc:self.results.put((None,str(exc)))
            threading.Thread(target=build,daemon=True).start()
        if not self.results.empty():
            result,error=self.results.get();self.loading=False
            if error:self.status.configure(text='Some photos could not be prepared. '+error)
            else:
                self.rows,self.checked=result;self.update_choices();self.selected.intersection_update({r['path'] for r in self.rows})
                if not service or not (service.running or self.app.scan_running):
                    group_count=len({r.get('proposal',{}).get('group_label') for r in self.rows if r.get('proposal',{}).get('group_label')})
                    self.status.configure(text=service.status+' Open Review Load Cards to retry.' if service and service.load_failure else f'{len(self.rows)} Photos Ready'+(f' · {group_count} Photo Groups Found' if group_count else ' to Review'))
                if not self.selected:self.render()
        self.job=self.win.after(250,self.poll)
    def filtered(self):
        rows=[]
        group_labels={g.get('group_label') for row in self.rows for g in (row.get('proposal',{}),row.get('review_group',{}))}
        for r in self.rows:
            category=self.category.get();load=self.load_filter.get()
            if category=='unreviewed' and (r['load'] or r['stage'] in PHASE):continue
            if category.startswith('stage:'):
                if (r.get('stage_proposal') or {}).get('stage')!=category.split(':')[1]:continue
            elif category not in ('all','unreviewed') and r['category']!=category:continue
            if load=='Not Assigned' and r['load']:continue
            is_group=load in group_labels
            if is_group and all(g.get('group_label')!=load for g in (r.get('proposal',{}),r.get('review_group',{}))):continue
            if load.startswith('Load ') and load.split()[-1].isdigit() and r['load']!=int(load.split()[-1]):continue
            if load.startswith('Suggested Load ') and r.get('proposal',{}).get('load')!=int(load.split()[-1]):continue
            if load=='Load Clues to Review' and not r.get('proposal'):continue
            if self.related is not None and r['path'] not in self.related:continue
            rows.append(r)
        if self.related is not None:rows.sort(key=lambda r:-self.related[r['path']])
        else:rows.sort(key=lambda r:r['sort_key'] if self.sort.get()=='Photo Date' else (r['position'],))
        return rows
    def reset_page(self):self.page=0;self.render()
    def move(self,n):self.page=max(0,self.page+n);self.render()
    def clear_selection(self):self.selected.clear();self.refresh_selection()
    def select_filtered(self):
        if self.app.case is not self.case:return
        rows=self.filtered()
        if not rows:return
        self.selected.update(r['path'] for r in rows);self.refresh_selection()
        self.review_help.configure(text=f'{len(rows)} filtered photos selected across all pages. Check the group before applying a load or stage.')
    def select_page(self):self.selected.update(r['path'] for r in self.visible);self.refresh_selection()
    def toggle(self,path):
        if path in self.selected:self.selected.remove(path)
        else:self.selected.add(path)
        self.refresh_selection()
    def refresh_selection(self):
        for path,(variable,button) in getattr(self,'selection_controls',{}).items():
            chosen=path in self.selected;variable.set(chosen)
            button.configure(text=('Selected' if chosen else 'Select Photo') if self.page_size.get()=='6' else '')
        filtered={r['path'] for r in self.filtered()};outside=len(self.selected-filtered)
        self.selection.configure(text=f'{len(self.selected)} Selected'+(f' · {outside} Outside Filter' if outside else ''))
        self.update_apply_state()
    def find_related(self):
        if len(self.selected)!=1:messagebox.showinfo('Choose One Photo','Select one example photo to find related views.',parent=self.win);return
        from review_assist import similar_views
        self.related=similar_views(next(iter(self.selected)),self.checked);self.reset_page()
    def change_category(self,category):
        if not self.selected or self.app.case is not self.case:return
        from review_assist import confirm_categories
        try:
            from review_actions import snapshot
            before=snapshot(self.case);paths=sorted(self.selected)
            confirm_categories(self.case,paths,category,self.checked);self.remember_batch(before,paths,'category');self.app.save()
            self.selected.clear();self.dirty=True;self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
        except Exception as exc:messagebox.showwarning('Photos Need Review',str(exc),parent=self.win)
    def mark_boundary(self,kind):
        if self.app.case is not self.case:self.close();return
        if len(self.selected)!=1 or not self.target.get().startswith('Load '):
            messagebox.showinfo('Choose a Load Photo','Select one photo and choose its load in the bottom bar first.',parent=self.win);return
        from load_identity import mark_sequence_anchor
        try:
            row=next(r for r in self.rows if r['path'] in self.selected)
            mark_sequence_anchor(self.case,row,int(self.target.get().split()[-1]),kind);self.app.save();self.selected.clear();self.dirty=True
            self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
        except Exception as exc:messagebox.showwarning('Boundary Needs Review',str(exc),parent=self.win)
    def clear_boundaries(self):
        if self.app.case is not self.case:self.close();return
        if not self.target.get().startswith('Load '):return
        n=int(self.target.get().split()[-1])
        for kind in ('start','end'):self.case.get('load_sequence_anchors',{}).pop(f'{n}:{kind}',None)
        self.app.save();self.dirty=True;self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
    def clear_related(self):self.related=None;self.reset_page()
    def add_load(self):
        self.app.add_load();self.app.save();self.update_choices();self.target.set(f"Load {len(self.case['loads'])}");self.app.e_load.set(str(len(self.case['loads'])));self.target_help()
    def render(self):
        for child in self.cards.winfo_children():child.destroy()
        self.images=[];self.check_vars=[];self.selection_controls={};rows=self.filtered()
        size=int(self.page_size.get());columns=3 if size==6 else 4 if size==12 else max(3,min(6,max(450,self.canvas.winfo_width())//145));grid_rows=(size+columns-1)//columns
        pages=max(1,(len(rows)+size-1)//size);self.page=min(self.page,pages-1)
        self.visible=rows[self.page*size:self.page*size+size]
        for index in range(6):self.cards.columnconfigure(index,weight=0,uniform='')
        for index in range(4):self.cards.rowconfigure(index,weight=0,uniform='')
        service=getattr(self.app,'_background_photos',None)
        if service and service.case is self.case:service.prioritize(r['path'] for r in self.visible)
        self.pager.configure(text=f'{self.page+1} / {pages}');self.refresh_selection()
        self.update_apply_state()
        if not rows:ttk.Label(self.cards,text='No photos in this group yet. Other groups remain available.',wraplength=460).pack(pady=30);return
        for i,r in enumerate(self.visible):
            card=ttk.Frame(self.cards,style='Card.TFrame',padding=8 if size==6 else 4);card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=4,pady=4)
            self.cards.columnconfigure(i%columns,weight=1,uniform='photos');self.cards.rowconfigure(i//columns,weight=1,uniform='rows')
            controls=ttk.Frame(card,style='Card.TFrame');controls.pack(side='bottom',fill='x')
            selected=tk.BooleanVar(self.win,value=r['path'] in self.selected);self.check_vars.append(selected)
            checkbox=ttk.Checkbutton(controls,text=('Selected' if r['path'] in self.selected else 'Select Photo') if size==6 else '',command=lambda p=r['path']:self.toggle(p),variable=selected);checkbox.pack(side='left');self.selection_controls[r['path']]=(selected,checkbox)
            ttk.Button(controls,text='Open',command=lambda p=r['path']:self.inspect([p])).pack(side='right')
            caption=(f"Load {r['load']}" if r['load'] else STAGES.get(r['stage'],'Not Assigned') if r['stage'] in PHASE else r.get('proposal',{}).get('reason','Load Not Assigned'))+'\n'+r['timing']
            if not r['load'] and r.get('stage_proposal') and r['stage'] not in PHASE:
                caption='Possible '+STAGES[r['stage_proposal']['stage']]+'\n'+r['timing']
            if r['load'] and r.get('proposal',{}).get('status') in ('conflict','card_mapping_conflict'):caption=f"Load {r['load']} · Card Needs Review\n"+r['timing']
            if size!=6:
                proposal=r.get('proposal',{});stage=r.get('stage_proposal',{}) or {}
                caption=f"Load {r['load']}" if r['load'] else 'Check Card '+str(proposal['vendor_load']) if proposal.get('vendor_load') else 'Possible '+STAGES[stage['stage']] if stage else STAGES.get(r['stage'],'Needs Review')
                if size==12:caption+='\n'+r['timing'].split(' · ')[0]
            locations=r.get('location_clues',[]) if size==6 else []
            if locations:caption+='\nLocation Text: '+locations[0]['text']
            ttk.Label(card,text=caption,style='Card.TLabel',wraplength=max(110,(self.cards.winfo_width()-30)//columns-20)).pack(side='bottom',anchor='w',pady=5 if size==6 else 2)
            try:
                if file_digest(r['path'])!=r['sha256']:raise ValueError('Photo changed; updating...')
                with Image.open(r['path']) as im:
                    im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((max(90,min(340,(max(400,self.canvas.winfo_width())-columns*18)//columns)),110 if size==24 else 150 if size==12 else 220));preview=ImageTk.PhotoImage(im)
                self.images.append(preview);label=ttk.Label(card,image=preview,style='Card.TLabel');label.pack(expand=True);label.bind('<Button-1>',lambda e,p=r['path']:self.toggle(p))
            except Exception as exc:ttk.Label(card,text=str(exc),wraplength=180).pack()
    def inspect(self,paths):
        from photo_inspector import inspect_photos
        return inspect_photos(self.win,paths)
    def compare_selected(self):
        if len(self.selected)!=2:
            messagebox.showinfo('Select Two Photos','Select exactly two photos to compare side by side.',parent=self.win);return
        self.inspect(sorted(self.selected))
    def apply(self):
        if not self.selected:return
        if self.target.get()=='Choose a Load or Stage':return
        if self.app.case is not self.case:self.close();return
        outside=len(self.selected-{r['path'] for r in self.filtered()})
        if outside and not messagebox.askyesno('Include Photos Outside This Filter?',f'{len(self.selected)} photos are selected, including {outside} outside the current filter. Apply this load or stage to all selected photos?',parent=self.win):return
        try:
            from review_actions import snapshot
            before=snapshot(self.case);paths=sorted(self.selected)
            target=self.target.get()
            if target.startswith('Load '):
                number=int(target.split()[-1]);confirm_load_membership(self.case,sorted(self.selected),number,self.checked);self.app.e_load.set(str(number))
            else:
                stage=next(key for key in PHASE if STAGES[key]==target)
                for path in self.selected:
                    if self.checked.get(path,{}).get('sha256')!=file_digest(path):raise ValueError('A selected photo changed. Inspect it again.')
                apply_visual_stage(self.case,sorted(self.selected),stage,visually_checked=True)
            self.remember_batch(before,paths,'assignment');self.app.save();self.selected.clear();self.dirty=True;self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
        except Exception as exc:messagebox.showwarning('Photos Need Review',str(exc),parent=self.win)
    def next_step(self):
        label=self.load_filter.get()
        if label.split()[-1].isdigit() and (label.startswith('Load ') or label.startswith('Suggested Load ')):self.app.e_load.set(label.split()[-1])
        elif self.target.get().startswith('Load ') and self.target.get().split()[-1].isdigit():self.app.e_load.set(self.target.get().split()[-1])
        elif label.startswith('Photo Group '):
            self.review_help.configure(text='Confirm this group’s load card, or choose its load in the bottom bar before filling the template.');self.target_box.focus_set();return
        self.close();self.app.template_photo_review()
    def close(self):
        if self.closed:return
        self.closed=True
        if self.resize_job:self.win.after_cancel(self.resize_job)
        if self.job:self.win.after_cancel(self.job)
        if self.bind_id:self.app.root.unbind('<<PhotoGroupsUpdated>>',self.bind_id)
        self.win.destroy()
