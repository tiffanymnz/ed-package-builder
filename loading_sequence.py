from ui_windows import fit_window
"""Review a load's stages together; commit explicit choices atomically."""
import copy
from pathlib import Path
from calculator_evidence import file_digest
STAGES=[('empty','Empty Container'),('quarter','Quarter Full'),('half','Half Full'),
        ('three_quarters','Three Quarters Full'),('full_1','Full · View 1'),('full_2','Full · View 2')]

def source_key(candidate):
    from template_review import pixel_digest
    try:return pixel_digest(candidate['path'])
    except (OSError,ValueError):return candidate.get('sha256') or candidate['path']

def propose_loading_sequence(case,index,load_number):
    from template_review import assigned_path
    if not 1<=load_number<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
    load=case['loads'][load_number-1];plan={};occupied=set();available={}
    for slot,label in STAGES:
        from load_requirements import stage_label
        label=stage_label(load,slot,label)
        path=assigned_path(load,slot);candidate=None
        if path:
            try:candidate=dict(path=path,name=Path(path).name,sha256=file_digest(path),basis='Currently Selected')
            except OSError:pass
        from load_requirements import applicable
        if not applicable(load,slot) and not candidate:
            plan[slot]=dict(label=label,candidate=None,current=False,alternatives=[],not_required=True);continue
        options,_=index.shortlist(case,load_number,slot,limit=12)
        plan[slot]=dict(label=label,candidate=candidate,current=bool(candidate),alternatives=options)
        if candidate:occupied.add(source_key(candidate));continue
        target='full' if slot.startswith('full_') else slot
        for choice in options:
            if choice.get('card_stage_unread'):continue
            if not (choice.get('reviewed_load_match') or choice.get('group_load_match')):continue
            scores=index.scores.get(choice['path'],{});score=scores.get(target,0)
            competing=max((scores.get(k,0) for k in ('empty','quarter','half','three_quarters','full') if k!=target),default=0)
            if choice.get('stage_conflict') or (choice.get('card_stage') and choice['card_stage']!=target):continue
            card_supported=choice.get('basis')=='Card Stage Evidence' and choice.get('card_stage')==target
            if not card_supported and (choice.get('basis')=='Check Loading Stage' or score<.15 or score<competing):continue
            key=source_key(choice);available.setdefault(key,[]).append((slot,choice,2 if card_supported else score-competing+.01))
    slots=[slot for slot,_ in STAGES if not plan[slot]['current']];bits={slot:1<<i for i,slot in enumerate(slots)}
    states={0:(0,{})}
    for key,choices in available.items():
        if key in occupied:continue
        updated=dict(states)
        for mask,(score,selected) in states.items():
            for slot,choice,value in choices:
                bit=bits[slot]
                if mask&bit:continue
                if score+value>updated.get(mask|bit,(-1,{}))[0]:updated[mask|bit]=(score+value,dict(selected,**{slot:choice}))
        states=updated
    _,selected=max(states.values(),key=lambda item:item[0])
    for slot,choice in selected.items():plan[slot]['candidate']=choice
    return plan

def apply_loading_sequence(case,load_number,selections):
    from template_review import assign_template_photo
    if not isinstance(selections,dict) or not selections:raise ValueError('Check the photos you have reviewed.')
    if set(selections)-{s for s,_ in STAGES}:raise ValueError('Choose loading stages only.')
    if not 1<=load_number<=len(case.get('loads',[])):raise ValueError('Choose an existing load.')
    prepared=copy.deepcopy(case)
    for slot in selections:
        prepared['loads'][load_number-1].setdefault('photos',{}).pop(slot,None)
        prepared.get('template_photo_reviews',{}).pop(f'{load_number}:{slot}',None)
    for slot,candidate in selections.items():
        if candidate is not None:assign_template_photo(prepared,load_number,slot,candidate)
    for candidate in selections.values():
        if candidate is not None and file_digest(candidate['path'])!=candidate.get('sha256'):raise ValueError('A photo changed. Inspect its current version.')
    case.clear();case.update(prepared)

class LoadingSequenceWindow:
    def __init__(self,parent):
        import tkinter as tk
        from tkinter import ttk
        self.parent=parent;self.app=parent.app;self.case=parent.case;self.number=parent.load.get();self.index=parent.index
        self.plan=propose_loading_sequence(self.case,self.index,self.number);self.choices={s:r['candidate'] for s,r in self.plan.items()}
        self.flags={};self.offsets={s:-1 for s,_ in STAGES};self.cleared=set();self.images=[];self.closed=False;self.resize_job=None
        self.win=tk.Toplevel(parent.win);self.win.title(f'Load {self.number} · Loading Sequence');self.win.transient(parent.win)
        self.win.geometry(f'{min(1120,self.win.winfo_screenwidth()-40)}x{min(820,self.win.winfo_screenheight()-70)}');self.win.minsize(880,620);fit_window(self.win,parent.win,(1120,820),(880,600))
        body=ttk.Frame(self.win,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text=f'Load {self.number} · Loading Sequence',font=(self.app.ui_font,20,'bold')).pack(anchor='w')
        ttk.Label(body,text='Compare the stages together. Check the photos that show the stated fill level. Leave missing evidence empty.',wraplength=960).pack(anchor='w',pady=(5,10))
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(10,0))
        self.status=ttk.Label(footer,text='No photos checked.',wraplength=550);self.status.pack(side='left')
        self.save_button=ttk.Button(footer,text='Save Checked Choices',style='Primary.TButton',command=self.apply,state='disabled');self.save_button.pack(side='right')
        self.grid=ttk.Frame(body);self.grid.pack(fill='both',expand=True)
        for i in range(3):self.grid.columnconfigure(i,weight=1,uniform='sequence')
        for i in range(2):self.grid.rowconfigure(i,weight=1,uniform='sequence')
        for slot,_ in STAGES:
            self.flags[slot]=tk.BooleanVar(value=False);self.flags[slot].trace_add('write',lambda *args:self.update_state())
        self.win.protocol('WM_DELETE_WINDOW',self.close);self.win.bind('<Configure>',self.resize);self.win.bind('<Destroy>',self.destroyed)
        self.win.after_idle(self.render)
    def resize(self,event):
        if event.widget is not self.win or self.closed:return
        if self.resize_job:self.win.after_cancel(self.resize_job)
        self.resize_job=self.win.after(150,self.render)
    def render(self):
        if self.closed:return
        from tkinter import ttk
        from PIL import Image,ImageOps,ImageTk
        self.resize_job=None
        for w in self.grid.winfo_children():w.destroy()
        self.images=[];width=max(180,(self.grid.winfo_width()-30)//3-20);height=max(65,min(215,(self.grid.winfo_height()-25)//2-105))
        for i,(slot,label) in enumerate(STAGES):
            card=ttk.Frame(self.grid,padding=8,style='Card.TFrame');card.grid(row=i//3,column=i%3,sticky='nsew',padx=3,pady=3)
            ttk.Label(card,text=self.plan[slot]['label'],font=(self.app.ui_font,12,'bold'),style='Card.TLabel').pack(anchor='w')
            preview=ttk.Frame(card,style='Card.TFrame');preview.pack(fill='both',expand=True);candidate=self.choices[slot];ready=False
            if candidate:
                try:
                    if file_digest(candidate['path'])!=candidate['sha256']:raise ValueError('Photo changed. Choose its current version.')
                    with Image.open(candidate['path']) as source:
                        picture=ImageOps.exif_transpose(source).convert('RGB');picture.thumbnail((width,height));picture=ImageTk.PhotoImage(picture)
                    self.images.append(picture);ttk.Label(preview,image=picture,style='Card.TLabel').pack(expand=True);ready=True
                except (OSError,ValueError) as exc:ttk.Label(preview,text=str(exc),wraplength=width,style='Card.TLabel').pack(expand=True)
            else:ttk.Label(preview,text='Stage Will Be Cleared' if slot in self.cleared else 'Not Required for This Partial Load' if self.plan[slot].get('not_required') else 'Needs a Photo',style='Card.TLabel').pack(expand=True)
            actions=ttk.Frame(card,style='Card.TFrame');actions.pack(side='bottom',fill='x')
            ttk.Checkbutton(actions,text='Checked' if candidate else 'Clear This Stage' if slot in self.cleared else 'Choose a Photo',variable=self.flags[slot],state='normal' if ready or slot in self.cleared else 'disabled').pack(anchor='w')
            buttons=ttk.Frame(actions,style='Card.TFrame');buttons.pack(fill='x',pady=(3,0))
            ttk.Button(buttons,text='Zoom',command=lambda s=slot:self.zoom(s),state='normal' if ready else 'disabled').pack(side='left')
            ttk.Button(buttons,text='Other Photos',command=lambda s=slot:self.other(s)).pack(side='left',padx=3)
            ttk.Button(buttons,text='Clear',command=lambda s=slot:self.clear(s)).pack(side='right')
    def update_state(self):
        count=sum(v.get() for v in self.flags.values());self.status.configure(text=f'{count} Choices Checked' if count else 'No photos checked.');self.save_button.configure(state='normal' if count else 'disabled')
    def other(self,slot):
        current=getattr(self,'picker',None)
        if current and not current.closed:current.win.destroy()
        self.picker=SequencePhotoPicker(self,slot)
    def choose(self,slot,candidate):
        self.choices[slot]=candidate;self.cleared.discard(slot);self.flags[slot].set(False);self.render()
    def clear(self,slot):self.choices[slot]=None;self.cleared.add(slot);self.flags[slot].set(True);self.render()
    def zoom(self,slot):
        if self.choices[slot]:
            from photo_inspector import inspect_photos
            inspect_photos(self.win,[self.choices[slot]['path']])
    def apply(self):
        if self.closed:return
        if self.app.case is not self.case:self.close();return
        try:
            apply_loading_sequence(self.case,self.number,{s:self.choices[s] for s,v in self.flags.items() if v.get()})
            self.app.save();self.parent.load.set(self.number);self.app.e_load.set(str(self.number));self.parent.refresh();self.close()
        except Exception as exc:self.status.configure(text=str(exc))
    def destroyed(self,event):
        if event.widget is self.win:
            self.closed=True
            if self.resize_job:
                try:self.win.after_cancel(self.resize_job)
                except Exception:pass
                self.resize_job=None
    def close(self):
        if self.closed:return
        self.win.destroy()


class SequencePhotoPicker:
    """Paged visual alternatives; never cycle blindly through filenames."""
    PAGE_SIZE=9
    def __init__(self,board,slot):
        import tkinter as tk
        from tkinter import ttk
        self.board=board;self.slot=slot;self.closed=False;self.page=0;self.images=[]
        self.win=tk.Toplevel(board.win);self.win.title('Choose a Loading Photo');self.win.transient(board.win);self.win.geometry('940x740');self.win.minsize(840,650);fit_window(self.win,board.win,(940,740),(840,600))
        body=ttk.Frame(self.win,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text=board.plan[slot]['label'],font=(board.app.ui_font,18,'bold')).pack(anchor='w')
        ttk.Label(body,text='Compare the alternatives. Select a photo, then check it on the loading sequence.').pack(anchor='w',pady=(4,8))
        self.browse=tk.BooleanVar(value=False)
        ttk.Checkbutton(body,text='Browse All Originals',variable=self.browse,command=self.reload).pack(anchor='w',pady=(0,6))
        foot=ttk.Frame(body);foot.pack(side='bottom',fill='x',pady=(8,0))
        self.prev=ttk.Button(foot,text='Previous Photos',command=lambda:self.move(-1));self.prev.pack(side='left')
        self.count=ttk.Label(foot,text='');self.count.pack(side='left',padx=12)
        self.next=ttk.Button(foot,text='Next Photos',command=lambda:self.move(1));self.next.pack(side='right')
        self.grid=ttk.Frame(body);self.grid.pack(fill='both',expand=True)
        for i in range(3):self.grid.columnconfigure(i,weight=1,uniform='picker');self.grid.rowconfigure(i,weight=1,uniform='picker')
        self.win.bind('<Destroy>',self.destroyed);self.reload()
    def reload(self):
        self.page=0
        self.options,_=self.board.index.shortlist(self.board.case,self.board.number,self.slot,browse_all=self.browse.get(),limit=max(12,len(self.board.case.get('imported_files',[]))))
        self.render()
    def render(self):
        from tkinter import ttk
        from PIL import Image,ImageOps,ImageTk
        if self.closed:return
        for child in self.grid.winfo_children():child.destroy()
        self.images=[];total=len(self.options);start=self.page*self.PAGE_SIZE
        for i,candidate in enumerate(self.options[start:start+self.PAGE_SIZE]):
            card=ttk.Frame(self.grid,padding=5,style='Card.TFrame');card.grid(row=i//3,column=i%3,sticky='nsew',padx=3,pady=3)
            try:
                if file_digest(candidate['path'])!=candidate.get('sha256'):raise ValueError('Photo Changed')
                with Image.open(candidate['path']) as source:
                    picture=ImageOps.exif_transpose(source).convert('RGB');picture.thumbnail((245,112));picture=ImageTk.PhotoImage(picture)
                self.images.append(picture);ttk.Label(card,image=picture,style='Card.TLabel').pack(expand=True)
                ttk.Label(card,text=Path(candidate['path']).name,wraplength=240,style='Card.TLabel').pack()
                actions=ttk.Frame(card,style='Card.TFrame');actions.pack(fill='x')
                ttk.Button(actions,text='Zoom',command=lambda c=candidate:self.zoom(c)).pack(side='left')
                ttk.Button(actions,text='Choose Photo',command=lambda c=candidate:self.choose(c)).pack(side='right')
            except (OSError,ValueError):ttk.Label(card,text='Photo Changed or Unavailable',wraplength=220).pack(expand=True)
        self.count.configure(text=f'{start+1}–{min(start+self.PAGE_SIZE,total)} of {total}' if total else 'No matching photos. Try Browse All Originals.')
        self.prev.configure(state='normal' if self.page else 'disabled');self.next.configure(state='normal' if start+self.PAGE_SIZE<total else 'disabled')
    def move(self,delta):
        self.page=max(0,min((max(1,len(self.options))-1)//self.PAGE_SIZE,self.page+delta));self.render()
    def zoom(self,candidate):
        from photo_inspector import inspect_photos
        inspect_photos(self.win,[candidate['path']])
    def choose(self,candidate):
        if self.board.closed:self.win.destroy();return
        if file_digest(candidate['path'])!=candidate.get('sha256'):self.reload();return
        self.board.choose(self.slot,candidate);self.win.destroy()
    def destroyed(self,event):
        if event.widget is self.win:self.closed=True
