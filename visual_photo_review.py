"""Visual confirmation workflow. Dates and filenames never determine a work stage."""
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageOps, ImageTk
from calculator_evidence import file_digest

STAGES = {'before': 'Before Removal', 'during': 'Removal in Progress', 'after': 'After Removal',
          'load': 'Container / Load Evidence', 'review': 'Needs Review'}
PHASE = {'before': 'before_photos', 'during': 'during_photos', 'after': 'after_photos'}
CRITERIA = {
    'before': 'The selected photos show the property and debris before removal.',
    'during': 'The selected photos show debris removal in progress at the property.',
    'after': 'The selected photos show cleared property areas after debris removal. One clean area alone does not establish that the entire property is clear.',
    'load': 'The selected photos document a container, measurement, load progression or disposal receipt. They do not establish the property work stage.',
}
DATE = r'(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})'
TIME = r'\d{1,2}:\d{2}(?::\d{2})?\s*\.?\s*(?:AM|PM)?'
MONTHS={name.lower():i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTHS.update({name[:3]:value for name,value in list(MONTHS.items())})
NAMED_DATE=r'(?:\b|(?<=day)|(?<=days))(?P<month>'+ '|'.join(sorted(MONTHS,key=len,reverse=True))+r')\s+(?P<day>\d{1,2})(?:\s*[, :]\s*|\s+)(?P<year>20\d{2})\b'

def normalize_date(raw):
    values = re.split(r'[-/.:]', raw)
    if len(values)!=3: return None
    try:
        if len(values[0])==4: year,month,day=map(int,values)
        else:
            month,day,year=map(int,values)
            if month<=12 and day<=12 and month!=day: return None
        return datetime(year,month,day).strftime('%Y-%m-%d')
    except ValueError: return None

def timing_clues(path, text=''):
    clues=[]
    try:
        with Image.open(path) as image:
            exif=image.getexif()
            raw=exif.get(36867)
            if not raw:
                try:raw=exif.get_ifd(34665).get(36867)
                except Exception:pass
        if raw:
            raw=str(raw).strip()
            try:
                value=datetime.strptime(raw,'%Y:%m:%d %H:%M:%S')
                clues.append(dict(source='Camera Metadata',value=value.strftime('%Y-%m-%d %H:%M:%S'),
                    date=value.strftime('%Y-%m-%d'),time=value.strftime('%H:%M:%S'),precision='Date and Time',verified=False))
            except ValueError:
                date=normalize_date(raw)
                if date:clues.append(dict(source='Camera Metadata',value=raw,date=date,time=None,precision='Date Only',verified=False))
    except Exception:pass
    seen=set()
    for match in re.finditer(r'(?P<date>'+DATE+r')(?:(?:[ T]+|\s*[.,]?\s*at\s*)(?P<time>'+TIME+r'))?',text,re.I):
        raw=match.group(0).strip()
        if raw in seen:continue
        seen.add(raw)
        time=None
        if match.group('time'):
            value=match.group('time').strip().upper().replace('.', '')
            for format in ('%H:%M:%S','%H:%M','%I:%M:%S %p','%I:%M %p','%I:%M:%S%p','%I:%M%p'):
                try:time=datetime.strptime(value,format).strftime('%H:%M:%S');break
                except ValueError:pass
        clues.append(dict(source='Photo Text (Unverified OCR)',value=raw,date=normalize_date(match.group('date')),time=time,
            precision='Date and Time' if match.group('time') else 'Date Only',verified=False))
    flags=[]
    for match in re.finditer(NAMED_DATE+r'(?:(?:[ T]+|\s*[.,]?\s*at\s*)(?P<clock>'+TIME+r'))?',text,re.I):
        try:date=datetime(int(match['year']),MONTHS[match['month'].lower()],int(match['day'])).strftime('%Y-%m-%d')
        except ValueError:continue
        clock=None
        if match['clock']:
            value=match['clock'].strip().upper().replace('.', '')
            for pattern in ('%H:%M:%S','%H:%M','%I:%M:%S %p','%I:%M %p','%I:%M:%S%p','%I:%M%p'):
                try:clock=datetime.strptime(value,pattern).strftime('%H:%M:%S');break
                except ValueError:pass
        clues.append(dict(source='Photo Text (Unverified OCR)',value=match.group(),date=date,time=clock,precision='Date and Time' if clock else 'Date Only',verified=False))
    dates={clue['date'] for clue in clues if clue['date']}
    if len(dates)>1:flags.append('Date Clues Differ - Review the Sources')
    if any(not clue['date'] for clue in clues):flags.append('Date Format Needs Review')
    if len({clue['time'] for clue in clues if clue['time']})>1 and len(dates)<=1:
        flags.append('Multiple Time Clues - Check Camera and Overlay Settings')
    return dict(clues=clues,flags=flags,note='Date/time supports sequence only. It does not establish Before, During or After.')

def current_stage(case,path):
    record=case.get('property_stage_reviews',{}).get(path,{})
    try:
        stat=Path(path).stat()
        if record.get('source_size')!=stat.st_size or record.get('source_mtime_ns')!=stat.st_mtime_ns:return 'review'
        if record.get('sha256')!=file_digest(path):return 'review'
        category=case.get('photo_category_examples',{}).get(path,{})
        if category.get('sha256')==record['sha256'] and category.get('category') not in (None,'property_photos'):return 'review'
    except OSError:return 'review'
    return record.get('stage','review') if record.get('visual_confirmed') else 'review'

def apply_visual_stage(case,paths,stage,visually_checked=False):
    if stage not in STAGES:raise ValueError('Choose a valid review category.')
    if stage!='review' and not visually_checked:raise ValueError('Visual confirmation is required; filenames and timestamps are not sufficient.')
    # Validate the whole batch before changing any case assignments.
    entries=[]
    for raw in dict.fromkeys(paths):
        path=str(raw)
        with Image.open(path) as image:image.verify()
        digest=file_digest(path)
        category=case.get('photo_category_examples',{}).get(path,{})
        if stage in PHASE and category.get('sha256')==digest and category.get('category') not in (None,'property_photos'):
            raise ValueError('A selected photo has a different reviewed object category. Correct or remove that category before assigning a property stage.')
        stat=Path(path).stat();entries.append((path,digest,stat.st_size,stat.st_mtime_ns))
    for path,digest,size,mtime in entries:
        for phase in PHASE.values():case[phase]=[p for p in case.get(phase,[]) if p!=path]
        if stage in PHASE:case.setdefault(PHASE[stage],[]).append(path)
        case.setdefault('property_stage_reviews',{})[path]=dict(stage=stage,visual_confirmed=stage!='review',
            sha256=digest,source_size=size,source_mtime_ns=mtime,reviewed_at=datetime.now(timezone.utc).isoformat(),
            basis='Reviewer inspected visible property condition; timing and filename are supporting clues only.')

def property_review_issues(case):
    issues=[]
    for stage,phase in PHASE.items():
        unreviewed=changed=category_conflicts=0
        for path in case.get(phase,[]):
            record=case.get('property_stage_reviews',{}).get(path,{})
            if not record.get('visual_confirmed') or record.get('stage')!=stage:unreviewed+=1;continue
            try:
                digest=file_digest(path)
                if record.get('sha256')!=digest:changed+=1
                category=case.get('photo_category_examples',{}).get(path,{})
                if category.get('sha256')==digest and category.get('category') not in (None,'property_photos'):category_conflicts+=1
            except Exception:changed+=1
        if unreviewed:issues.append(f'{STAGES[stage]}: visually review {unreviewed} property photo(s).')
        if changed:issues.append(f'{STAGES[stage]}: {changed} reviewed photo file(s) changed or are missing; review them again.')
        if category_conflicts:issues.append(f'{STAGES[stage]}: {category_conflicts} photo category conflict(s); compare the original and correct the category or work stage.')
    return issues

class PhotoReviewWindow:
    PAGE_SIZE=12
    def __init__(self,app):
        self.app=app;self.case=app.case;self.selected=set();self.page=0;self.images=[]
        self.records=[r for r in self.case.get('imported_files',[]) if Path(r['path']).suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}]
        self.search=tk.StringVar();self.group_by=tk.StringVar(value='All Photos');self.group=tk.StringVar(value='All Groups')
        self.page_size=tk.IntVar(value=24);self.PAGE_SIZE=24
        self.stage_index={r['path']:current_stage(self.case,r['path']) for r in self.records}
        self.best_only=tk.BooleanVar(value=False)
        self.similarity_anchor=None;self.similarity_scores={}
        self.refresh_assistance(build_ui=False)
        self.date_index={r['path']:next((c['date'] for c in timing_clues(r['path'],self.case.get('photo_text_cache',{}).get(r['path'],{}).get('text',''))['clues'] if c['date']),'Date Not Available') for r in self.records}
        self.win=tk.Toplevel(app.root);self.win.title('Visual Photo Review');self.win.geometry('1060x760');self.win.minsize(900,600)
        self.win.transient(app.root)
        self.body=ttk.Frame(self.win,padding=18);self.body.pack(fill='both',expand=True)
        ttk.Label(self.body,text='Review Photos',font=(app.ui_font,19,'bold')).pack(anchor='w')
        ttk.Label(self.body,text='Before: debris present before removal. During: removal in progress. After: property cleared of debris. Container loading is separate evidence.',wraplength=760).pack(anchor='w',pady=(6,4))
        ttk.Label(self.body,text='Dates and times are supporting clues. A date-only photo is usable; filenames and dates never confirm a stage.',wraplength=760,style='Muted.TLabel').pack(anchor='w',pady=(0,12))
        controls=ttk.Frame(self.body);controls.pack(fill='x',pady=(0,10))
        self.filter=tk.StringVar(value='Needs Review')
        box=ttk.Combobox(controls,textvariable=self.filter,values=['All Photos']+list(STAGES.values()),state='readonly',width=25)
        box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda event:self.reset_page())
        self.page_label=ttk.Label(controls,text='');self.page_label.pack(side='left',padx=14)
        ttk.Button(controls,text='Select This Page',command=self.select_page).pack(side='right',padx=8)
        ttk.Button(controls,text='Next',command=lambda:self.move(1)).pack(side='right',padx=8)
        ttk.Button(controls,text='Previous',command=lambda:self.move(-1)).pack(side='right')
        groups=ttk.Frame(self.body);groups.pack(fill='x',pady=(0,10))
        ttk.Label(groups,text='Group By').pack(side='left')
        group_by=ttk.Combobox(groups,textvariable=self.group_by,values=['All Photos','Capture Date','Source Folder','Assigned Load','Document Type','Suggested Category','Similar Photos','Similar to Selection','Possible Load','Suggested Stage'],state='readonly',width=18);group_by.pack(side='left',padx=6)
        self.group_box=ttk.Combobox(groups,textvariable=self.group,values=['All Groups'],state='readonly',width=24);self.group_box.pack(side='left')
        ttk.Button(groups,text='Correct Category',command=self.correct_category).pack(side='right')
        group_by.bind('<<ComboboxSelected>>',lambda event:self.update_groups())
        self.group_box.bind('<<ComboboxSelected>>',lambda event:self.reset_page())
        search_row=ttk.Frame(self.body);search_row.pack(fill='x',pady=(0,10))
        ttk.Label(search_row,text='Find a Filename').pack(side='left')
        entry=ttk.Entry(search_row,textvariable=self.search,width=24);entry.pack(side='left',padx=8);entry.bind('<Return>',lambda event:self.reset_page())
        ttk.Button(search_row,text='Find',command=self.reset_page).pack(side='left')
        ttk.Button(search_row,text='Select Group',command=self.select_group).pack(side='right')
        sizes=ttk.Combobox(search_row,textvariable=self.page_size,values=[12,24,48],state='readonly',width=4);sizes.pack(side='right',padx=6)
        ttk.Label(search_row,text='Photos per Page').pack(side='right')
        sizes.bind('<<ComboboxSelected>>',lambda event:self.change_size())
        review_tools=ttk.Frame(self.body);review_tools.pack(fill='x',pady=(0,8))
        ttk.Checkbutton(review_tools,text='Show Best Shots',variable=self.best_only,command=self.reset_page).pack(side='left')
        ttk.Button(review_tools,text='Refresh Matches',command=self.refresh_assistance).pack(side='left',padx=8)
        ttk.Button(review_tools,text='Find Similar Photos',command=self.find_similar).pack(side='left')
        ttk.Button(review_tools,text='Use Suggested Stage',command=self.use_suggested_stage).pack(side='right')
        self.load_choice=tk.StringVar(value='Choose Load')
        ttk.Button(review_tools,text='Assign to Load',command=self.assign_load).pack(side='right',padx=6)
        ttk.Combobox(review_tools,textvariable=self.load_choice,values=['Choose Load']+[str(i) for i in range(1,len(self.case.get('loads',[]))+1)],state='readonly',width=12).pack(side='right')
        self.assist_summary=ttk.Label(self.body,text='',style='Muted.TLabel',wraplength=950);self.assist_summary.pack(anchor='w',pady=(0,5))
        actions=ttk.Frame(self.body);actions.pack(side='bottom',fill='x',pady=(12,0))
        self.selection_label=ttk.Label(actions,text='0 Selected');self.selection_label.pack(side='left')
        self.target=tk.StringVar(value='Needs Review')
        ttk.Combobox(actions,textvariable=self.target,values=list(STAGES.values()),state='readonly',width=25).pack(side='left',padx=12)
        ttk.Button(actions,text='Apply to Selected',style='Primary.TButton',command=self.apply).pack(side='left')
        ttk.Button(actions,text='Close',command=self.close).pack(side='right')
        ttk.Button(actions,text='Clear Selection',command=self.clear_selection).pack(side='right',padx=8)
        self.canvas=tk.Canvas(self.body,highlightthickness=0,background='#f2f5f8')
        scroll=ttk.Scrollbar(self.body,command=self.canvas.yview);scroll.pack(side='right',fill='y');self.canvas.pack(fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.grid=ttk.Frame(self.canvas);self.window=self.canvas.create_window((0,0),window=self.grid,anchor='nw')
        self.grid.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.window,width=event.width))
        self.win.bind('<MouseWheel>',lambda event:self.canvas.yview_scroll(int(-event.delta/120) or (-1 if event.delta>0 else 1),'units'))
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.render()

    def filtered(self):
        records=[r for r in self.records if
            (self.filter.get()=='All Photos' or STAGES.get(self.stage_index.get(r['path']),'Needs Review')==self.filter.get()) and
            (self.group.get()=='All Groups' or self.group_key(r)==self.group.get()) and
            self.search.get().strip().lower() in r.get('name',Path(r['path']).name).lower() and
            (not self.best_only.get() or r['path'] not in self.assistance['repeats']['index'] or r['path'] in self.assistance['repeats']['keep'])]
        if self.group_by.get()=='Similar to Selection':
            records=[r for r in records if r['path'] in self.similarity_scores]
            records.sort(key=lambda r:(-self.similarity_scores[r['path']],r['path']))
        return records

    def group_key(self,record):
        path=record['path'];kind=self.group_by.get()
        if kind=='Capture Date':return self.date_index[path]
        if kind=='Source Folder':
            source=record.get('source','')
            return str(PurePosixPath(source.replace('\\','/')).parent) if source else 'Source Folder Not Available'
        if kind=='Assigned Load':
            tag=self.case.get('photo_load_assignments',{}).get(path,{})
            confirmed=[str(tag['load'])] if tag.get('sha256')==self.current_rows.get(path,{}).get('sha256') and tag.get('load') else []
            loads=[str(i) for i,load in enumerate(self.case.get('loads',[]),1) if path in list(load.get('photos',{}).values())+[load.get('disposal_photo'),load.get('evidence_first_10_cyd')]+load.get('extra_measurement_photos',[])]
            loads=sorted(set(loads+confirmed),key=int)
            return 'Load '+', '.join(loads) if loads else 'Load Not Assigned'
        if kind=='Suggested Category':return self.suggestion_index[path]
        if kind=='Similar to Selection':return 'Related Views' if path in self.similarity_scores else 'Other Photos'
        if kind=='Similar Photos':
            group=self.assistance['repeats']['index'].get(path,{})
            return group['id']+f" ({group['count']} Photos)" if group.get('count',0)>1 else 'Single / Unanalyzed Photos'
        if kind=='Possible Load':return self.assistance['matches'].get(path,{}).get('load_group','No Load Clue')
        if kind=='Suggested Stage':return self.assistance['matches'].get(path,{}).get('stage_group','Stage Needs Review')
        if kind=='Document Type':
            from cor_package import ROLES
            roles=[ROLES.get(d.get('role'),'Other Document') for d in self.case.get('package_documents',[]) if d['path']==path]
            return ', '.join(sorted(set(roles))) if roles else 'Photo / Purpose Not Assigned'
        return 'All Photos'

    def refresh_assistance(self,build_ui=True):
        from review_assist import checked_rows,build_review_index
        from local_photo_sorter import MODEL_DIGEST,VERSION,LABELS
        self.current_rows=checked_rows(self.records,self.case.get('local_photo_results',{}),MODEL_DIGEST,VERSION)
        known={r['path'] for r in self.records}
        for path,entry in self.case.get('photo_category_examples',{}).items():
            if path not in known or path in self.current_rows:continue
            try:
                if file_digest(path)==entry.get('sha256'):self.current_rows[path]={'sha256':entry['sha256']}
            except OSError:pass
        if self.similarity_anchor:
            from review_assist import similar_views
            self.similarity_scores=similar_views(self.similarity_anchor,self.current_rows)
        self.assistance=build_review_index(self.records,self.current_rows,self.case)
        self.suggestion_index={r['path']:LABELS.get(self.assistance['categories'][r['path']]['category'],'Not Analyzed') for r in self.records}
        self.stage_index={r['path']:current_stage(self.case,r['path']) for r in self.records}
        if build_ui:self.update_groups()

    def correct_category(self):
        if self.app.case is not self.case:
            messagebox.showinfo('Case Changed','Reopen photo review for the current case.',parent=self.win);return
        if not self.selected:
            messagebox.showinfo('Select Photos','Select a few photos of the same type, then choose Correct Category.',parent=self.win);return
        from review_assist import CATEGORY_LABELS,confirm_categories
        paths=sorted(self.selected)
        snapshots=dict(self.current_rows)
        try:
            for path in paths:
                if path not in snapshots:snapshots[path]={'sha256':file_digest(path)}
        except OSError as exc:
            messagebox.showerror('Photo Unavailable',str(exc),parent=self.win);return
        dialog=tk.Toplevel(self.win);dialog.title('Correct Photo Category');dialog.geometry('530x300');dialog.transient(self.win)
        body=ttk.Frame(dialog,padding=22);body.pack(fill='both',expand=True)
        title='What Does This Photo Show?' if len(paths)==1 else f'What Do These {len(paths)} Photos Show?'
        ttk.Label(body,text=title,font=(self.app.ui_font,15,'bold')).pack(anchor='w')
        ttk.Label(body,text='Your checked examples help group similar photos in this case. This does not assign a load or Before / During / After stage.',wraplength=480).pack(anchor='w',pady=12)
        choice=tk.StringVar(value='Choose a Category')
        ttk.Combobox(body,textvariable=choice,values=list(CATEGORY_LABELS.values()),state='readonly',width=32).pack(anchor='w',pady=6)
        def apply():
            if choice.get() not in CATEGORY_LABELS.values():return
            if self.app.case is not self.case:
                dialog.destroy();return
            category=next(key for key,value in CATEGORY_LABELS.items() if value==choice.get())
            if not messagebox.askyesno('Confirm Photo Category',f'Have you checked that all {len(paths)} selected photos show {choice.get().lower()}?',parent=dialog):return
            try:
                confirm_categories(self.case,paths,category,snapshots)
                self.app.save();self.refresh_assistance();self.selected.clear();self.selection_label.configure(text='0 Selected');self.render();dialog.destroy()
            except Exception as exc:messagebox.showerror('Category Not Saved',str(exc),parent=dialog)
        def clear_examples():
            if self.app.case is not self.case:dialog.destroy();return
            for path in paths:self.case.get('photo_category_examples',{}).pop(path,None)
            self.app.save();self.refresh_assistance();dialog.destroy()
        actions=ttk.Frame(body);actions.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(actions,text='Remove Saved Category',command=clear_examples).pack(side='left')
        ttk.Button(actions,text='Save Category',style='Primary.TButton',command=apply).pack(side='right')

    def find_similar(self):
        if self.app.case is not self.case:
            messagebox.showinfo('Case Changed','Reopen photo review for the current case.',parent=self.win);return
        if len(self.selected)!=1:
            messagebox.showinfo('Select One Example','Select one photo, then choose Find Similar Photos.',parent=self.win);return
        from review_assist import similar_views
        self.refresh_assistance(build_ui=False)
        anchor=next(iter(self.selected));scores=similar_views(anchor,self.current_rows)
        if not scores:
            messagebox.showinfo('Photo Analysis Needed','Run local photo sorting for this photo and the photos to compare, then try again.',parent=self.win);return
        self.similarity_anchor=anchor;self.similarity_scores=scores
        self.selection_label.configure(text=f'{len(self.selected)} Selected')
        self.group_by.set('Similar to Selection');self.filter.set('All Photos');self.search.set('');self.best_only.set(False)
        self.update_groups();self.group.set('Related Views');self.reset_page()

    def show_repeat_set(self,path):
        group=self.assistance['repeats']['index'].get(path)
        if not group:return
        self.best_only.set(False);self.filter.set('All Photos');self.search.set('')
        self.group_by.set('Similar Photos');self.update_groups();self.group.set(group['id']+f" ({group['count']} Photos)");self.reset_page()

    def use_suggested_stage(self):
        stages={self.assistance['matches'].get(path,{}).get('stage') for path in self.selected}
        if len(stages)!=1 or None in stages:
            messagebox.showinfo('Choose a Suggested Group','Select photos with the same suggested stage. Confirm a few Before, During and After examples first, then Refresh Matches.',parent=self.win);return
        self.target.set(STAGES[next(iter(stages))]);self.apply()

    def assign_load(self):
        if self.app.case is not self.case:messagebox.showinfo('Case Changed','Reopen photo review for the current case.',parent=self.win);return
        if not self.selected:messagebox.showinfo('Select Photos','Select the photos that belong to one load.',parent=self.win);return
        raw=self.load_choice.get()
        if raw=='Choose Load':
            choices={tuple(self.assistance['matches'].get(path,{}).get('loads',[])) for path in self.selected}
            if len(choices)!=1 or len(next(iter(choices)))!=1:
                messagebox.showinfo('Choose a Load','Choose the load number for the selected photos.',parent=self.win);return
            raw=str(next(iter(choices))[0])
        try:
            from review_assist import confirm_load_membership
            from calculator_evidence import file_digest
            snapshots=dict(self.current_rows)
            for path in self.selected:
                if path not in snapshots:snapshots[path]={'sha256':file_digest(path)}
            if not messagebox.askyesno('Confirm Load',f'Assign {len(self.selected)} selected photos to Load {raw}?\n\nCheck load labels and the actual sequence. Similar containers or timestamps alone do not establish the load. Evidence slots will stay unchanged.',parent=self.win):return
            self.app.save();confirm_load_membership(self.case,sorted(self.selected),int(raw),snapshots)
            self.app.save();self.refresh_assistance();self.selected.clear();self.selection_label.configure(text='0 Selected');self.render()
        except Exception as exc:messagebox.showerror('Load Assignment Failed',str(exc),parent=self.win)

    def update_groups(self):
        values=['All Groups']+sorted({self.group_key(r) for r in self.records})
        self.group_box.configure(values=values);self.group.set('All Groups');self.reset_page()

    def change_size(self):self.PAGE_SIZE=self.page_size.get();self.reset_page()

    def select_group(self):
        self.selected.update(r['path'] for r in self.filtered())
        self.selection_label.configure(text=f'{len(self.selected)} Selected');self.render()

    def reset_page(self):self.page=0;self.render()
    def select_page(self):
        for record in self.filtered()[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE]:self.selected.add(record['path'])
        self.selection_label.configure(text=f'{len(self.selected)} Selected');self.render()
    def clear_selection(self):
        self.selected.clear();self.selection_label.configure(text='0 Selected');self.render()
    def move(self,amount):
        pages=max(1,(len(self.filtered())+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        self.page=max(0,min(pages-1,self.page+amount));self.render()

    def toggle(self,path,value):
        if value.get():self.selected.add(path)
        else:self.selected.discard(path)
        self.selection_label.configure(text=f'{len(self.selected)} Selected')

    def render(self):
        for widget in self.grid.winfo_children():widget.destroy()
        self.images=[];records=self.filtered();pages=max(1,(len(records)+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        sets=sum(len(g['members'])>1 for g in self.assistance['repeats']['groups'])
        hidden=len(self.records)-len([r for r in self.records if r['path'] not in self.assistance['repeats']['index'] or r['path'] in self.assistance['repeats']['keep']])
        self.assist_summary.configure(text=f'{sets} similar-photo sets · Best Shots can hide {hidden} repeat views. Originals stay available. Confirm a few stage examples, then Refresh Matches.')
        learned=sum(row['basis']=='From Your Examples' for row in self.assistance['categories'].values())
        conflicts=sum(row['basis']=='Category Conflict' for row in self.assistance['categories'].values())
        if learned or conflicts:self.assist_summary.configure(text=f'{learned} category suggestions from your examples · {conflicts} category conflicts to review · {sets} similar-photo sets. Categories do not confirm a work stage or load.')
        if self.group_by.get()=='Similar to Selection':
            self.assist_summary.configure(text=f'{len(records)} related views, closest first. Check the visible contents before assigning a stage or load. Similarity alone does not confirm either.')
        self.page=min(self.page,pages-1);self.page_label.configure(text=f'Page {self.page+1} of {pages} · {len(records)} Photos')
        for i,record in enumerate(records[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE]):
            path=record['path'];card=ttk.Frame(self.grid,style='Card.TFrame',padding=10)
            card.grid(row=i//3,column=i%3,sticky='nsew',padx=5,pady=5);self.grid.columnconfigure(i%3,weight=1,uniform='photo')
            flag=tk.BooleanVar(value=path in self.selected)
            ttk.Checkbutton(card,text=STAGES.get(self.stage_index.get(path),'Needs Review'),variable=flag,command=lambda p=path,v=flag:self.toggle(p,v)).pack(anchor='w')
            try:
                with Image.open(path) as image:
                    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((225,140));preview=ImageTk.PhotoImage(image)
                self.images.append(preview);ttk.Label(card,image=preview,style='Card.TLabel').pack(pady=6)
            except Exception:ttk.Label(card,text='Preview Unavailable',style='Card.TLabel').pack(pady=24)
            ttk.Label(card,text=record.get('name',Path(path).name),style='Card.TLabel',wraplength=220).pack(anchor='w')
            suggestion=self.suggestion_index.get(path,'Not Analyzed')
            if suggestion!='Not Analyzed':
                basis=self.assistance['categories'].get(path,{}).get('basis')
                caption=('Reviewed: ' if basis=='Reviewed Category' else 'Suggested: ')+suggestion
                if basis in ('From Your Examples','Category Conflict'):caption+=' · '+basis
                ttk.Label(card,text=caption,style='Card.TLabel',foreground='#086879',wraplength=220).pack(anchor='w',pady=4)
            group=self.assistance['repeats']['index'].get(path,{})
            if group.get('count',0)>1:
                ttk.Label(card,text=('Suggested Copy · ' if group.get('recommended') else 'Repeat View · ')+str(group['count'])+' Photos',style='Card.TLabel',wraplength=220).pack(anchor='w')
                ttk.Button(card,text='Compare All Photos',command=lambda p=path:self.show_repeat_set(p)).pack(anchor='w',pady=3)
            match=self.assistance['matches'].get(path,{})
            if match.get('loads'):
                ttk.Label(card,text='Possible Load '+', '.join(map(str,match['loads']))+' · '+match['load_basis'],style='Card.TLabel',wraplength=220).pack(anchor='w',pady=3)
            if match.get('stage'):ttk.Label(card,text='Suggested: '+match['stage_group']+' (Example Match)',style='Card.TLabel',wraplength=220).pack(anchor='w',pady=3)
            text=self.case.get('photo_text_cache',{}).get(path,{}).get('text','')
            clues=timing_clues(path,text)
            caption='\n'.join(f"{c['source']}: {c['value']}"+(' · No Time Shown' if c['precision']=='Date Only' else '') for c in clues['clues']) or 'No Capture Date / Time Found'
            if clues['flags']:caption+='\n'+'\n'.join(clues['flags'])
            ttk.Label(card,text=caption,style='Card.TLabel',foreground='#61738a',wraplength=220).pack(anchor='w',pady=5)
            ttk.Button(card,text='Open Full Photo',command=lambda p=path:self.app.open_original(p)).pack(anchor='w')
        if not records:ttk.Label(self.grid,text='No photos in this category. Import files or choose another filter.').pack(pady=35)
        self.canvas.yview_moveto(0)

    def apply(self):
        if self.app.case is not self.case:messagebox.showinfo('Case Changed','Reopen photo review for the current case.',parent=self.win);return
        if not self.selected:messagebox.showinfo('Select Photos','Select the thumbnails you have visually checked.',parent=self.win);return
        stage=next(key for key,value in STAGES.items() if value==self.target.get())
        if stage!='review' and not messagebox.askyesno('Confirm Visible Conditions',
            f"{len(self.selected)} Selected Photos\n\n{CRITERIA[stage]}\n\nHave you checked every selected photo visually? Dates and filenames alone are not sufficient.",parent=self.win):return
        try:
            self.app.save();apply_visual_stage(self.case,sorted(self.selected),stage,visually_checked=stage!='review')
            self.app.save();self.app.refresh_assignments();self.app.show_checks()
            self.stage_index={r['path']:current_stage(self.case,r['path']) for r in self.records}
            self.refresh_assistance(build_ui=False)
            self.selected.clear();self.selection_label.configure(text='0 Selected');self.render()
        except Exception as exc:messagebox.showerror('Photo Review Failed',str(exc),parent=self.win)

    def close(self):
        self.app.save();self.app.refresh_assignments();self.app.show_checks();self.win.destroy()
