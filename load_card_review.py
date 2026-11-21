from ui_windows import fit_window
"""Fast source-checked card review before bulk photo organization."""
import tkinter as tk
from tkinter import ttk,messagebox
from load_groups import card_candidates,confirm_card
from photo_inspector import PhotoPane

class CardReviewWindow:
    def __init__(self,app):
        self.app=app;self.case=app.case;self.rows=[];self.preview=None;self.shown_key=None;self.closed=False;self.form_defaults={};app._load_card_review=self
        self.win=tk.Toplevel(app.root);self.win.title('Review Load Cards');self.win.geometry(f'{max(850,min(1080,app.root.winfo_screenwidth()-40))}x{max(620,min(780,app.root.winfo_screenheight()-60))}');self.win.minsize(850,620);self.win.transient(app.root);fit_window(self.win,app.root,(1080,780),(850,600));self.win.configure(background=app.root.cget('bg'))
        body=ttk.Frame(self.win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Review Load Cards',font=(app.ui_font,21,'bold')).pack(anchor='w')
        intro=ttk.Label(body,text='Check the number and stage on the card, then choose its load in this package. Vendor numbering may differ from package numbering.',wraplength=970);intro.pack(fill='x',pady=(6,12))
        intro.bind('<Configure>',lambda e:intro.configure(wraplength=max(240,e.width)))
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(12,0))
        self.hide_button=ttk.Button(footer,text='Hide Card from Suggestions',command=self.dismiss);self.hide_button.pack(side='left')
        ttk.Button(footer,text='Review Photo Groups',command=self.groups).pack(side='right')
        self.confirm_button=ttk.Button(footer,text='Confirm Load Card',style='Primary.TButton',command=self.confirm);self.confirm_button.pack(side='right',padx=8)
        controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,10))
        ttk.Label(controls,text='Number on Card (If Shown)').pack(side='left');self.vendor_number=tk.StringVar()
        ttk.Spinbox(controls,from_=1,to=150,textvariable=self.vendor_number,width=6).pack(side='left',padx=(8,16))
        ttk.Label(controls,text='Package Load').pack(side='left');self.number=tk.StringVar()
        ttk.Spinbox(controls,from_=1,to=150,textvariable=self.number,width=6).pack(side='left',padx=8)
        stage_controls=ttk.Frame(body);stage_controls.pack(fill='x',pady=(0,10))
        ttk.Label(stage_controls,text='Loading Stage Shown').pack(side='left')
        self.stage=tk.StringVar(value='Not Clear / Not Shown')
        self.stage_names={'Not Clear / Not Shown':None,'Empty':'empty','Quarter Full':'quarter','Half Full':'half','Three Quarters Full':'three_quarters','Full':'full'}
        ttk.Combobox(stage_controls,textvariable=self.stage,values=list(self.stage_names),state='readonly',width=26).pack(side='left',padx=8)
        self.use_stage_button=ttk.Button(stage_controls,text='Use Suggested Stage',command=self.use_suggested_stage,state='disabled');self.use_stage_button.pack(side='left',padx=8)
        self.status=ttk.Label(body,text='',wraplength=970);self.status.pack(fill='x',pady=(0,8))
        self.status.bind('<Configure>',lambda e:self.status.configure(wraplength=max(240,e.width)))
        queue_controls=ttk.Frame(body);queue_controls.pack(fill='x',pady=(0,8))
        self.queue_summary=ttk.Label(queue_controls,text='');self.queue_summary.pack(side='left')
        self.show_reviewed=tk.BooleanVar(value=False)
        ttk.Checkbutton(queue_controls,text='Show Reviewed Cards',variable=self.show_reviewed,command=lambda:self.refresh(preserve=True)).pack(side='right')
        self.retry_button=ttk.Button(queue_controls,text='Retry Card Reading',command=self.retry_reading,state='disabled');self.retry_button.pack(side='right',padx=8)
        self.reading_status=ttk.Label(body,text='',wraplength=970);self.reading_status.pack(fill='x',pady=(0,8));self.reading_status.bind('<Configure>',lambda e:self.reading_status.configure(wraplength=max(240,e.width)))
        self.show_hidden=tk.BooleanVar(value=False)
        ttk.Checkbutton(queue_controls,text='Show Hidden Cards',variable=self.show_hidden,command=lambda:self.refresh(preserve=True)).pack(side='right',padx=6)
        content=ttk.Panedwindow(body,orient='horizontal');content.pack(fill='both',expand=True)
        left=ttk.Frame(content);right=ttk.Frame(content);content.add(left,weight=1);content.add(right,weight=3);self.right=right
        self.tree=ttk.Treeview(left,columns=('load',),show='tree headings',selectmode='browse');self.tree.heading('#0',text='Card');self.tree.heading('load',text='Package Load');self.tree.column('#0',width=160);self.tree.column('load',width=90)
        scroll=ttk.Scrollbar(left,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',lambda e:self.show())
        self.binding=app.root.bind('<<PhotoGroupsUpdated>>',lambda e:self.refresh(preserve=True),add='+')
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();app.start_photo_work()
    def refresh(self,preserve=False):
        if self.closed:return
        if self.app.case is not self.case:self.close();return
        if not self.win.winfo_exists():return
        old=self.selected() if self.rows else None
        candidates=card_candidates(self.case,include_hidden=self.show_hidden.get())
        pending=sum(not r.get('reviewed_load') and not r.get('hidden') for r in candidates)
        reviewed=sum(bool(r.get('reviewed_load')) and not r.get('hidden') for r in candidates)
        self.queue_summary.configure(text=f'{pending} Card'+('' if pending==1 else 's')+f' to Review · {reviewed} Confirmed')
        self.rows=[r for r in candidates if self.show_reviewed.get() or not r.get('reviewed_load') or r.get('hidden')]
        self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.rows):self.tree.insert('','end',iid=str(i),text=row.get('name','Card'),values=('Hidden' if row.get('hidden') else row.get('reviewed_load') or 'To Review',))
        target=next((str(i) for i,r in enumerate(self.rows) if not r.get('reviewed_load') and not r.get('hidden')),None)
        if preserve and old:target=next((str(i) for i,r in enumerate(self.rows) if r['path']==old['path']),target)
        if target is None and self.rows:target='0'
        service=getattr(self.app,'_background_photos',None)
        service=service if service and service.case is self.case else None
        running=bool(service and service.running) or bool(getattr(self.app,'scan_running',False))
        self.reading_status.configure(text=service.status if service else '')
        self.retry_button.configure(state='normal' if service and getattr(service,'load_failure',False) and not service.reader_running and not service.closed and not service.cancel.is_set() else 'disabled')
        if target is not None:
            self.tree.selection_set(target);self.tree.see(target);self.show()
        else:
            self.shown_key=None;self.form_defaults={}
            for child in self.right.winfo_children():child.destroy()
            self.preview=None;self.number.set('');self.vendor_number.set('');self.stage.set('Not Clear / Not Shown')
            self.confirm_button.configure(state='disabled');self.hide_button.configure(state='disabled');self.use_stage_button.configure(state='disabled')
            self.status.configure(text='No unreviewed cards currently available. Reading continues; you can review photo groups.' if running else 'All available cards are reviewed. Continue to Review Photo Groups.' if reviewed else 'No load-card candidates found. You can continue reviewing photo groups.')
    def selected(self):
        selection=self.tree.selection()
        if not selection:return None
        try:return self.rows[int(selection[0])]
        except (ValueError,IndexError):return None
    def show(self):
        row=self.selected()
        if not row:return
        key=(row['path'],row['sha256']);same=key==self.shown_key
        values={'number':self.number.get(),'vendor':self.vendor_number.get(),'stage':self.stage.get()}
        dirty={name:same and value!=self.form_defaults.get(name) for name,value in values.items()}
        if not same:
            self.shown_key=key
            for child in self.right.winfo_children():child.destroy()
            self.preview=PhotoPane(self.right,row['path'],card_regions=row.get('card_regions',[]));self.preview.pack(fill='both',expand=True)
        elif self.preview is not None:self.preview.card_regions=row.get('card_regions',[])
        from card_evidence import reviewed_card_mapping
        mapped=row.get('reviewed_load') or reviewed_card_mapping(self.case,row['path'])
        record=self.case.get('load_card_reviews',{}).get(row['path'],{})
        stored=record.get('stage') if record.get('sha256')==row['sha256'] and record.get('confirmed') else None
        defaults={'number':str(mapped) if mapped else '',
                  'vendor':str(row.get('reviewed_vendor') or row['options'][0]) if row.get('reviewed_vendor') or len(row.get('options',[]))==1 else '',
                  'stage':next((label for label,value in self.stage_names.items() if value==stored),'Not Clear / Not Shown')}
        for name,var in [('number',self.number),('vendor',self.vendor_number),('stage',self.stage)]:
            if not dirty[name]:var.set(defaults[name])
        self.form_defaults=defaults
        hints=[]
        if len(row.get('options',[]))==1:hints.append('Possible Card Number: '+str(row['options'][0]))
        elif len(row.get('options',[]))>1:hints.append('Card Number Readings Disagree')
        stage=row.get('stage_suggestion')
        if stage in self.stage_names.values() and stage is not None:hints.append('Possible Stage: '+next(label for label,value in self.stage_names.items() if value==stage))
        elif row.get('stage_status')=='conflict':hints.append('Stage Readings Disagree')
        confirmed=bool(record.get('confirmed') and record.get('sha256')==row['sha256'])
        summary=f'Confirmed Package Load {mapped}' if confirmed else ''
        if confirmed and record.get('vendor_load') is not None:summary+=' · Card Number '+str(record['vendor_load'])
        if confirmed and stored:summary+=' · '+next(label for label,value in self.stage_names.items() if value==stored)
        self.status.configure(text='Hidden card: confirm it to include it again.' if row.get('hidden') else summary+'. Edit and confirm again to change this review.' if confirmed else ' · '.join(hints)+'. Check the photo, then confirm its package load.' if hints else 'Read the card and choose its package load. Leave it unconfirmed if unclear.')
        self.confirm_button.configure(text='Save Card Changes' if confirmed else 'Confirm Load Card')
        self.confirm_button.configure(state='normal');self.hide_button.configure(state='normal')
        self.use_stage_button.configure(state='normal' if stage is not None and stage in self.stage_names.values() else 'disabled')
    def use_suggested_stage(self):
        row=self.selected()
        if not row or self.app.case is not self.case:return
        from calculator_evidence import file_digest
        try:current=file_digest(row['path'])==row['sha256']
        except OSError:current=False
        if not current:
            messagebox.showwarning('Photo Changed or Missing','Restore or reimport this source photo, then inspect it before using its stage suggestion.',parent=self.win);return
        stage=row.get('stage_suggestion')
        if stage is not None and stage in self.stage_names.values():self.stage.set(next(label for label,value in self.stage_names.items() if value==stage))
    def retry_reading(self):
        service=getattr(self.app,'_background_photos',None)
        if service and service.case is self.case:service.retry_reading();self.refresh(preserve=True)
    def confirm(self):
        row=self.selected()
        if not row or self.app.case is not self.case:return
        try:
            try:n=int(self.number.get());vendor=int(self.vendor_number.get()) if self.vendor_number.get().strip() else None
            except ValueError:raise ValueError('Choose a package load. Enter a card number only when one is shown.')
            if vendor is None and self.stage_names[self.stage.get()] is None:raise ValueError('Enter the number shown on the card or choose its clearly visible loading stage.')
            if not 1<=n<=150:raise ValueError('Enter a load number from 1 to 150.')
            if n>len(self.case['loads']) and not messagebox.askyesno('Add Loads',f'Add empty Loads {len(self.case["loads"])+1} through {n}? Measurements and evidence will still need to be checked.',parent=self.win):return
            confirm_card(self.case,row['path'],n,expected_sha=row['sha256'],vendor_number=vendor,stage=self.stage_names[self.stage.get()]);self.changed();self.refresh()
        except Exception as exc:messagebox.showwarning('Check the Load Card',str(exc),parent=self.win)
    def dismiss(self):
        row=self.selected()
        if not row or self.app.case is not self.case:return
        from calculator_evidence import file_digest
        try:current=file_digest(row['path'])==row['sha256']
        except OSError:current=False
        if not current:messagebox.showwarning('Photo Changed','Inspect the current photo before reviewing it.',parent=self.win);return
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
