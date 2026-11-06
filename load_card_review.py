"""Fast source-checked card review before bulk photo organization."""
import tkinter as tk
from tkinter import ttk,messagebox
from load_groups import card_candidates,confirm_card
from photo_inspector import PhotoPane

class CardReviewWindow:
    def __init__(self,app):
        self.app=app;self.case=app.case;self.rows=[];self.preview=None;self.shown_key=None;self.closed=False;app._load_card_review=self
        self.win=tk.Toplevel(app.root);self.win.title('Review Load Cards');self.win.geometry(f'{max(850,min(1080,app.root.winfo_screenwidth()-40))}x{max(620,min(780,app.root.winfo_screenheight()-60))}');self.win.minsize(850,620);self.win.transient(app.root);self.win.configure(background=app.root.cget('bg'))
        body=ttk.Frame(self.win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Review Load Cards',font=(app.ui_font,21,'bold')).pack(anchor='w')
        ttk.Label(body,text='Check the number on the card, then choose its load in this package. Vendor numbering may differ from package numbering.',wraplength=970).pack(anchor='w',pady=(6,12))
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(footer,text='Hide Card from Suggestions',command=self.dismiss).pack(side='left')
        ttk.Button(footer,text='Review Photo Groups',command=self.groups).pack(side='right')
        ttk.Button(footer,text='Confirm Load Card',style='Primary.TButton',command=self.confirm).pack(side='right',padx=8)
        controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,10))
        ttk.Label(controls,text='Number on Card').pack(side='left');self.vendor_number=tk.StringVar()
        ttk.Spinbox(controls,from_=1,to=150,textvariable=self.vendor_number,width=6).pack(side='left',padx=(8,16))
        ttk.Label(controls,text='Package Load').pack(side='left');self.number=tk.StringVar()
        ttk.Spinbox(controls,from_=1,to=150,textvariable=self.number,width=6).pack(side='left',padx=8)
        stage_controls=ttk.Frame(body);stage_controls.pack(fill='x',pady=(0,10))
        ttk.Label(stage_controls,text='Loading Stage Shown on Card').pack(side='left')
        self.stage=tk.StringVar(value='Not Clear / Not Shown')
        self.stage_names={'Not Clear / Not Shown':None,'Empty':'empty','Quarter Full':'quarter','Half Full':'half','Three Quarters Full':'three_quarters','Full':'full'}
        ttk.Combobox(stage_controls,textvariable=self.stage,values=list(self.stage_names),state='readonly',width=26).pack(side='left',padx=8)
        self.status=ttk.Label(controls,text='',wraplength=450);self.status.pack(side='left',padx=12)
        self.show_hidden=tk.BooleanVar(value=False)
        ttk.Checkbutton(body,text='Show Hidden Cards',variable=self.show_hidden,command=lambda:(setattr(self,'shown_key',None),self.refresh())).pack(anchor='w',pady=(0,8))
        content=ttk.Panedwindow(body,orient='horizontal');content.pack(fill='both',expand=True)
        left=ttk.Frame(content);right=ttk.Frame(content);content.add(left,weight=1);content.add(right,weight=3);self.right=right
        self.tree=ttk.Treeview(left,columns=('load',),show='tree headings',selectmode='browse');self.tree.heading('#0',text='Card');self.tree.heading('load',text='Reviewed Load');self.tree.column('#0',width=160);self.tree.column('load',width=90)
        scroll=ttk.Scrollbar(left,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',lambda e:self.show())
        self.binding=app.root.bind('<<PhotoGroupsUpdated>>',lambda e:self.refresh(preserve=True),add='+')
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();app.start_photo_work()
    def refresh(self,preserve=False):
        if self.closed:return
        if self.app.case is not self.case:self.close();return
        if not self.win.winfo_exists():return
        old=self.selected() if self.rows else None;old_number=self.number.get();old_vendor=self.vendor_number.get();old_stage=self.stage.get()
        self.rows=card_candidates(self.case,include_hidden=self.show_hidden.get());self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.rows):self.tree.insert('','end',iid=str(i),text=row.get('name','Card'),values=('Hidden' if row.get('hidden') else row.get('reviewed_load') or 'Not Confirmed',))
        target=next((str(i) for i,r in enumerate(self.rows) if not r.get('reviewed_load')),None)
        if preserve and old:
            target=next((str(i) for i,r in enumerate(self.rows) if r['path']==old['path']),target)
        if target is None and self.rows:target='0'
        if target is not None:
            self.tree.selection_set(target);self.show()
            if preserve and old and self.selected()['path']==old['path']:self.number.set(old_number);self.vendor_number.set(old_vendor);self.stage.set(old_stage)
        else:self.status.configure(text='No load-card candidates yet. You can continue organizing photos while scanning finishes.')
    def selected(self):return self.rows[int(self.tree.selection()[0])] if self.tree.selection() else None
    def show(self):
        row=self.selected()
        if not row:return
        key=(row['path'],row['sha256'])
        if key==self.shown_key:return
        self.shown_key=key
        for child in self.right.winfo_children():child.destroy()
        self.preview=PhotoPane(self.right,row['path']);self.preview.pack(fill='both',expand=True)
        from card_evidence import reviewed_card_mapping
        mapped=row.get('reviewed_load') or reviewed_card_mapping(self.case,row['path'])
        self.number.set(str(mapped) if mapped else '')
        record=self.case.get('load_card_reviews',{}).get(row['path'],{})
        stored=record.get('stage') if record.get('sha256')==row['sha256'] and record.get('confirmed') else None
        self.stage.set(next((label for label,value in self.stage_names.items() if value==stored),'Not Clear / Not Shown'))
        self.vendor_number.set(str(row.get('reviewed_vendor') or row['options'][0]) if row.get('reviewed_vendor') or len(row.get('options',[]))==1 else '')
        self.status.configure(text=('Hidden card: confirm it to include it again.' if row.get('hidden') else 'Card reads Load '+str(row['options'][0])+'. Choose the corresponding package load.' if len(row.get('options',[]))==1 else 'Read the card and choose its package load. Leave it unconfirmed if unclear.'))
    def confirm(self):
        row=self.selected()
        if not row or self.app.case is not self.case:return
        try:
            try:n=int(self.number.get());vendor=int(self.vendor_number.get())
            except ValueError:raise ValueError('Enter the number shown on the card and its load number in this package.')
            if not 1<=n<=150:raise ValueError('Enter a load number from 1 to 150.')
            if n>len(self.case['loads']) and not messagebox.askyesno('Add Loads',f'Add empty Loads {len(self.case["loads"])+1} through {n}? Measurements and evidence will still need to be checked.',parent=self.win):return
            confirm_card(self.case,row['path'],n,expected_sha=row['sha256'],vendor_number=vendor,stage=self.stage_names[self.stage.get()]);self.changed();self.refresh()
        except Exception as exc:messagebox.showwarning('Check the Load Card',str(exc),parent=self.win)
    def dismiss(self):
        row=self.selected()
        if not row or self.app.case is not self.case:return
        from calculator_evidence import file_digest
        if file_digest(row['path'])!=row['sha256']:messagebox.showwarning('Photo Changed','Inspect the current photo before reviewing it.',parent=self.win);return
        self.case.setdefault('load_card_dismissals',{})[row['path']]=dict(sha256=row['sha256']);self.changed();self.refresh()
    def changed(self):
        self.app.save()
        self.app.case_caption.set(str(self.case.get('case_number',''))+' · '+str(len(self.case['loads']))+' Loads')
        self.app.root.event_generate('<<PhotoGroupsUpdated>>',when='tail')
    def groups(self):
        self.close();self.app.organize_photos()
    def close(self):
        if self.closed:return
        self.closed=True
        if getattr(self.app,'_load_card_review',None) is self:self.app._load_card_review=None
        if getattr(self,'binding',None):self.app.root.unbind('<<PhotoGroupsUpdated>>',self.binding);self.binding=None
        self.win.destroy()
