"""Visual confirmation workflow. Dates and filenames never determine a work stage."""
import re
from datetime import datetime, timezone
from pathlib import Path
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
TIME = r'\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?'

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
    for match in re.finditer(r'(?P<date>'+DATE+r')(?:[ T]+(?P<time>'+TIME+r'))?',text,re.I):
        raw=match.group(0).strip()
        if raw in seen:continue
        seen.add(raw)
        time=None
        if match.group('time'):
            value=match.group('time').strip().upper()
            for format in ('%H:%M:%S','%H:%M','%I:%M:%S %p','%I:%M %p','%I:%M:%S%p','%I:%M%p'):
                try:time=datetime.strptime(value,format).strftime('%H:%M:%S');break
                except ValueError:pass
        clues.append(dict(source='Photo Text (Unverified OCR)',value=raw,date=normalize_date(match.group('date')),time=time,
            precision='Date and Time' if match.group('time') else 'Date Only',verified=False))
    flags=[]
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
        unreviewed=changed=0
        for path in case.get(phase,[]):
            record=case.get('property_stage_reviews',{}).get(path,{})
            if not record.get('visual_confirmed') or record.get('stage')!=stage:unreviewed+=1;continue
            try:
                if record.get('sha256')!=file_digest(path):changed+=1
            except Exception:changed+=1
        if unreviewed:issues.append(f'{STAGES[stage]}: visually review {unreviewed} property photo(s).')
        if changed:issues.append(f'{STAGES[stage]}: {changed} reviewed photo file(s) changed or are missing; review them again.')
    return issues

class PhotoReviewWindow:
    PAGE_SIZE=12
    def __init__(self,app):
        self.app=app;self.case=app.case;self.selected=set();self.page=0;self.images=[]
        self.records=[r for r in self.case.get('imported_files',[]) if Path(r['path']).suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}]
        self.win=tk.Toplevel(app.root);self.win.title('Visual Photo Review');self.win.geometry('1060x760');self.win.minsize(900,600)
        self.win.transient(app.root)
        self.body=ttk.Frame(self.win,padding=18);self.body.pack(fill='both',expand=True)
        ttk.Label(self.body,text='Review the Property Condition',font=(app.ui_font,19,'bold')).pack(anchor='w')
        ttk.Label(self.body,text='Before: debris present before removal. During: removal in progress. After: property cleared of debris. Container loading is separate evidence.',wraplength=760).pack(anchor='w',pady=(6,4))
        ttk.Label(self.body,text='Dates and times are supporting clues. A date-only photo is usable; filenames and dates never confirm a stage.',wraplength=760,style='Muted.TLabel').pack(anchor='w',pady=(0,12))
        controls=ttk.Frame(self.body);controls.pack(fill='x',pady=(0,10))
        self.filter=tk.StringVar(value='All Photos')
        box=ttk.Combobox(controls,textvariable=self.filter,values=['All Photos']+list(STAGES.values()),state='readonly',width=25)
        box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda event:self.reset_page())
        self.page_label=ttk.Label(controls,text='');self.page_label.pack(side='left',padx=14)
        ttk.Button(controls,text='Select This Page',command=self.select_page).pack(side='right',padx=8)
        ttk.Button(controls,text='Next',command=lambda:self.move(1)).pack(side='right',padx=8)
        ttk.Button(controls,text='Previous',command=lambda:self.move(-1)).pack(side='right')
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
        if self.filter.get()=='All Photos':return self.records
        return [r for r in self.records if STAGES.get(current_stage(self.case,r['path']),'Needs Review')==self.filter.get()]

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
        self.page=min(self.page,pages-1);self.page_label.configure(text=f'Page {self.page+1} of {pages} · {len(records)} Photos')
        for i,record in enumerate(records[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE]):
            path=record['path'];card=ttk.Frame(self.grid,style='Card.TFrame',padding=10)
            card.grid(row=i//3,column=i%3,sticky='nsew',padx=5,pady=5);self.grid.columnconfigure(i%3,weight=1,uniform='photo')
            flag=tk.BooleanVar(value=path in self.selected)
            ttk.Checkbutton(card,text=STAGES.get(current_stage(self.case,path),'Needs Review'),variable=flag,command=lambda p=path,v=flag:self.toggle(p,v)).pack(anchor='w')
            try:
                with Image.open(path) as image:
                    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((225,140));preview=ImageTk.PhotoImage(image)
                self.images.append(preview);ttk.Label(card,image=preview,style='Card.TLabel').pack(pady=6)
            except Exception:ttk.Label(card,text='Preview Unavailable',style='Card.TLabel').pack(pady=24)
            ttk.Label(card,text=record.get('name',Path(path).name),style='Card.TLabel',wraplength=220).pack(anchor='w')
            text=self.case.get('photo_text_cache',{}).get(path,{}).get('text','')
            clues=timing_clues(path,text)
            caption='\n'.join(f"{c['source']}: {c['value']}"+(' · No Time Shown' if c['precision']=='Date Only' else '') for c in clues['clues']) or 'No Capture Date / Time Found'
            if clues['flags']:caption+='\n'+'\n'.join(clues['flags'])
            ttk.Label(card,text=caption,style='Card.TLabel',foreground='#61738a',wraplength=220).pack(anchor='w',pady=5)
            ttk.Button(card,text='Open Full Photo',command=lambda p=path:self.app.open_original(p)).pack(anchor='w')
        if not records:ttk.Label(self.grid,text='No photos in this category. Import files or choose another filter.').pack(pady=35)
        self.canvas.yview_moveto(0)

    def apply(self):
        if not self.selected:messagebox.showinfo('Select Photos','Select the thumbnails you have visually checked.',parent=self.win);return
        stage=next(key for key,value in STAGES.items() if value==self.target.get())
        if stage!='review' and not messagebox.askyesno('Confirm Visible Conditions',
            f"{len(self.selected)} Selected Photos\n\n{CRITERIA[stage]}\n\nHave you checked every selected photo visually? Dates and filenames alone are not sufficient.",parent=self.win):return
        try:
            self.app.save();apply_visual_stage(self.case,sorted(self.selected),stage,visually_checked=stage!='review')
            self.app.save();self.app.refresh_assignments();self.app.show_checks()
            self.selected.clear();self.selection_label.configure(text='0 Selected');self.render()
        except Exception as exc:messagebox.showerror('Photo Review Failed',str(exc),parent=self.win)

    def close(self):
        self.app.save();self.app.refresh_assignments();self.app.show_checks();self.win.destroy()
