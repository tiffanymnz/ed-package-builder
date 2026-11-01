"""Import-first user workflow for a complete ED COR package."""
import hashlib
import json
import queue
import re
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import guided_ui
from guided_ui import GuidedApp, SLOT_LABELS, BG, MUTED, ACCENT
from ed_app import BASE, make_case, default_load, safe, IMAGE_EXT
from ed_builder import volume
from calculator_evidence import screenshot_status
from cor_package import ROLES, document_suggestions, photo_suggestion, validate, assemble, description, totals, number
from local_reader import read_image
from visual_photo_review import PhotoReviewWindow, property_review_issues, apply_visual_stage, PHASE, CRITERIA
SLOT_LABELS.update({key: value.title().replace('Cyd', 'CYD').replace('Pdf', 'PDF') for key,value in SLOT_LABELS.items()})

guided_ui.STEPS[:] = [('Import Files', 'Start with the vendor files. No measurements or pricing required yet.'),
                     ('Review Loads', 'Match the photos, then confirm only the details that need your input.'),
                     ('Review Costs', 'Review bids, the invoice and the fixed first-10-CYD allowance.'),
                     ('Create Package', 'Review the complete package and export one combined COR draft.')]

class PackageApp(GuidedApp):
    def __init__(self, root):
        self.scan_running = False
        super().__init__(root)
        root.title('ED Package Builder | COR Workspace v20')
        self.status.set('Create a case with its case number and vendor, then import your files.')
        def add_load_text_tool(widget):
            if isinstance(widget,ttk.Menubutton):
                menu=widget.nametowidget(str(widget['menu']))
                menu.add_command(label='Review Load Text Suggestions',command=self.review_suggestions)
            for child in widget.winfo_children():add_load_text_tool(child)
        add_load_text_tool(root)

    def refresh(self):
        if self.case:
            known={item['path'] for item in self.case.get('package_documents',[])}
            records=list(self.case.get('imported_files',[]))
            records.extend(dict(path=p,name=Path(p).name) for p in self.case.get('financial_pdfs',[]) if p not in {r['path'] for r in records})
            for record in records:
                if record['path'] in known or Path(record['path']).suffix.lower() not in ('.pdf','.docx','.txt'):continue
                try:self.case.setdefault('package_documents',[]).extend(document_suggestions(record))
                except Exception:self.case.setdefault('package_documents',[]).append(dict(path=record['path'],name=record.get('name',Path(record['path']).name),role='other',pages='',confirmed=False,amount='',vendor=''))
                known.add(record['path'])
        super().refresh()

    def update_guide(self):
        super().update_guide()
        if self.current_step()==3: self.next_button.configure(text='Export COR Package')

    def open_original(self,path):
        if not path:messagebox.showinfo('Select a Photo','Select a source photo first.');return
        import os,sys,subprocess
        try:
            if sys.platform=='win32':os.startfile(str(path))
            else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)])
        except Exception as exc:messagebox.showerror('Cannot Open Source',str(exc))

    def new_case(self):
        if self.case: self.save()
        win=tk.Toplevel(self.root);win.title('New Case');win.geometry('480x330');win.transient(self.root);win.grab_set()
        body=ttk.Frame(win,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Create a Case',font=(self.ui_font,20,'bold')).pack(anchor='w')
        ttk.Label(body,text='Just the essentials. Add files next.',style='Muted.TLabel').pack(anchor='w',pady=(6,20))
        values={}
        for label,key in [('Case Number','case_number'),('Vendor','vendor')]:
            row=ttk.Frame(body);row.pack(fill='x',pady=8);ttk.Label(row,text=label,width=15).pack(side='left')
            var=tk.StringVar();values[key]=var;ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        def create():
            case=values['case_number'].get().strip();vendor=values['vendor'].get().strip()
            if not case or not vendor: messagebox.showwarning('Required Details','Enter the case number and vendor.',parent=win);return
            directory=BASE/safe(case)
            if (directory/'case.json').exists():messagebox.showwarning('Case Already Exists','Use Open to continue this case.',parent=win);return
            self.case=make_case(case,'',vendor,1,'');self.case['verified_first_10_amount']='300'
            self.case_dir=directory;self.vars={};self.save();self.refresh();self.go(0);win.destroy()
        ttk.Button(body,text='Create Case',style='Primary.TButton',command=create).pack(anchor='e',pady=22)

    def draw_case(self):
        if not self.case:self.empty(self.case_tab);return
        self.clear(self.case_tab)
        header=self.card(self.case_tab,'Import the Vendor Files','Import the folder or ZIP you received. The app keeps the originals and prepares document suggestions for review.')
        row=ttk.Frame(header,style='Card.TFrame');row.pack(fill='x',pady=6)
        ttk.Button(row,text='Import Folder',style='Primary.TButton',command=self.import_files).pack(side='left')
        ttk.Button(row,text='Import ZIPs',command=self.import_zips).pack(side='left',padx=8)
        ttk.Button(row,text='Find Load Details',command=self.scan_photos).pack(side='left')
        count=len(self.case.get('imported_files',[]))
        ttk.Label(header,text=f'{count} Files Imported  ·  {len(self.case["loads"])} Load(s)',style='Card.TLabel',foreground=ACCENT).pack(anchor='w',pady=(12,0))
        ttk.Label(self.case_tab,text='Package Documents',font=(self.ui_font,13,'bold')).pack(anchor='w',pady=(0,6))
        ttk.Label(self.case_tab,text='Open a row to confirm its purpose. One PDF can be split into sections by page range.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
        actions=ttk.Frame(self.case_tab);actions.pack(side='bottom',fill='x',pady=12)
        ttk.Button(actions,text='Review Document',command=self.edit_document).pack(side='left')
        ttk.Button(actions,text='Add Document',command=self.add_document).pack(side='left',padx=8)
        ttk.Button(actions,text='Visual Photo Review',command=self.visual_photo_review).pack(side='left')
        listing=ttk.Frame(self.case_tab);listing.pack(fill='both',expand=True)
        self.documents=ttk.Treeview(listing,columns=('role','pages','status'),show='tree headings',height=6)
        tree=self.documents
        for key,title,width in [('#0','File',260),('role','Include As',155),('pages','Pages',65),('status','Review',90)]:
            tree.heading(key,text=title);tree.column(key,width=width,minwidth=50,stretch=key in ('#0','role'))
        scroll=ttk.Scrollbar(listing,command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill='both',expand=True)
        for i,item in enumerate(self.case.get('package_documents',[])):
            tree.insert('','end',iid=str(i),text=item.get('name',Path(item['path']).name),values=(ROLES.get(item.get('role'),'Choose Purpose'),item.get('pages') or 'All','Confirmed' if item.get('confirmed') else 'Review'))
        tree.bind('<Double-1>',lambda event:self.edit_document())

    def _import_paths(self, files):
        super()._import_paths(files)
        existing={item['path'] for item in self.case.get('package_documents',[])}
        for item in self.case.get('imported_files',[]):
            if item['path'] in existing or Path(item['path']).suffix.lower() not in ('.pdf','.docx','.txt'):continue
            try:self.case.setdefault('package_documents',[]).extend(document_suggestions(item))
            except Exception:self.case.setdefault('package_documents',[]).append(dict(path=item['path'],name=item['name'],role='other',pages='',confirmed=False,amount='',vendor=''))
        suggestions=[photo_suggestion(item) for item in self.case.get('imported_files',[]) if Path(item['path']).suffix.lower() in IMAGE_EXT]
        self.case['photo_suggestions']=suggestions
        self.save();self.refresh();self.go(0)
        self.status.set('Files Imported. Review the document rows, then continue to Review Loads.')
        if any(Path(record['path']).suffix.lower() in IMAGE_EXT for record in self.case.get('imported_files',[])):self.scan_photos()

    def add_document(self):
        paths=filedialog.askopenfilenames(title='Add Package Documents',filetypes=[('Documents','*.pdf *.png *.jpg *.jpeg *.docx')])
        if paths:self._import_paths([Path(p) for p in paths])

    def edit_document(self):
        selected=self.documents.selection()
        if not selected:messagebox.showinfo('Select a Document','Select a document row first.');return
        index=int(selected[0]);item=self.case['package_documents'][index]
        win=tk.Toplevel(self.root);win.title('Review Package Document');win.geometry('640x500');win.transient(self.root);win.grab_set()
        body=ttk.Frame(win,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text=item.get('name','Document'),font=(self.ui_font,13,'bold'),wraplength=570).pack(anchor='w',pady=(0,10))
        def open_source():
            import os,sys,subprocess
            try:
                if sys.platform=='win32':os.startfile(item['path'])
                else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',item['path']])
            except Exception as exc:messagebox.showerror('Cannot Open Document',str(exc),parent=win)
        ttk.Button(body,text='Open Original Document',command=open_source).pack(anchor='w',pady=(0,15))
        role=tk.StringVar(value=ROLES.get(item.get('role'),'Supporting Document'))
        ttk.Label(body,text='Include As').pack(anchor='w');ttk.Combobox(body,textvariable=role,values=list(ROLES.values()),state='readonly',width=45).pack(anchor='w',pady=5)
        values={}
        for label,key in [('Pages (Blank = Entire File)','pages'),('Bid Total ($) - For Bids Only','amount'),('Bidder - For Bids Only','vendor')]:
            row=ttk.Frame(body);row.pack(fill='x',pady=7);ttk.Label(row,text=label,width=31).pack(side='left')
            var=tk.StringVar(value=item.get(key,''));values[key]=var;ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        def confirm(split=False):
            record=dict(item,role=next(key for key,value in ROLES.items() if value==role.get()),confirmed=True,**{key:value.get().strip() for key,value in values.items()})
            try:
                import fitz
                from cor_package import parse_pages
                if Path(record['path']).suffix.lower()=='.pdf':
                    with fitz.open(record['path']) as source:parse_pages(record.get('pages'),len(source))
                if record['role']=='bid':number(record['amount'])
            except Exception as exc:messagebox.showwarning('Check Document Details',str(exc),parent=win);return
            if split:self.case['package_documents'].append(record)
            else:self.case['package_documents'][index]=record
            self.case['bid_review_confirmed']=False;self.save();self.draw_case();win.destroy()
        row=ttk.Frame(body);row.pack(fill='x',pady=20)
        ttk.Button(row,text='Add as Another Section',command=lambda:confirm(True)).pack(side='left')
        ttk.Button(row,text='Confirm Document',style='Primary.TButton',command=confirm).pack(side='right')

    def scan_photos(self):
        if not self.require() or self.scan_running:return
        self.save();records=list(self.case.get('imported_files',[]));case_dir=self.case_dir
        cache=dict(self.case.get('photo_text_cache',{}))
        self.scan_running=True;results=queue.Queue();self.status.set('Reading Photo Text Locally... You can continue working.')
        def work():
            rows=[];notes=[]
            for item in records:
                if Path(item['path']).suffix.lower() not in IMAGE_EXT:continue
                cached=cache.get(item['path'])
                if cached and cached.get('sha256')==item.get('sha256'):
                    text,error=cached['text'],cached['error']
                else:
                    text,error=read_image(item['path'])
                    cache[item['path']]=dict(sha256=item.get('sha256'),text=text,error=error)
                row=photo_suggestion(item,text);row['reader_note']=error
                rows.append(row)
                if error:notes.append(error)
            results.put((rows,notes))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            if results.empty():self.root.after(150,poll);return
            rows,notes=results.get();self.scan_running=False
            if self.case_dir!=case_dir:return
            self.case['photo_suggestions']=rows;self.case['photo_text_cache']=cache;self.save()
            self.status.set('Photo Reading Complete. Open Visual Photo Review to inspect conditions and date clues.' if not notes else 'Some text could not be read. Visual Photo Review remains available; date-only photos are usable.')
            # Reading text never assigns the property stage or interrupts work with a popup.
        self.root.after(150,poll)

    def review_suggestions(self):
        rows=self.case.get('photo_suggestions',[])
        win=tk.Toplevel(self.root);win.title('Review Photo Suggestions');win.geometry('800x520');win.transient(self.root)
        body=ttk.Frame(win,padding=20);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Suggestions Need Your Review',font=(self.ui_font,17,'bold')).pack(anchor='w')
        ttk.Label(body,text='Select rows you have checked. Only labeled measurements are suggested; unreadable tape measures require manual input.',wraplength=740).pack(anchor='w',pady=10)
        tree=ttk.Treeview(body,columns=('load','purpose','dimensions'),show='tree headings',selectmode='extended')
        for key,label,width in [('#0','File',240),('load','Load',55),('purpose','Photo Purpose',170),('dimensions','Measurements',200)]:tree.heading(key,text=label);tree.column(key,width=width,minwidth=40)
        tree.pack(fill='both',expand=True)
        for i,row in enumerate(rows):
            dims=', '.join(f'{key.replace("_ft","")}: {value}' for key,value in row['dimensions'].items())
            tree.insert('','end',iid=str(i),text=row['name'],values=(row.get('load') or 'Unclear',SLOT_LABELS.get(row.get('slot'),'Review Manually'),dims))
        def apply():
            selected=tree.selection()
            if not selected:return
            if not messagebox.askyesno('Apply Reviewed Suggestions','Have you checked these photos and their load numbers? Existing assignments and entered measurements will not be overwritten.',parent=win):return
            self.save()
            for ident in selected:
                row=rows[int(ident)];n=row.get('load')
                if not n or not 1<=n<=150:continue
                while len(self.case['loads'])<n:self.case['loads'].append(default_load(len(self.case['loads'])+1))
                load=self.case['loads'][n-1]
                if row.get('slot'):load.setdefault('photos',{}).setdefault(row['slot'],row['path'])
                for key,value in row['dimensions'].items():
                    if not load.get(key):load[key]=value
                load['measurement_source']='Reviewed Photo Text';load['measurements_confirmed']=False
            self.save();self.refresh();win.destroy();self.go(1)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=15)
        ttk.Button(actions,text='Open Selected Photo',command=lambda:self.open_original(rows[int(tree.selection()[0])]['path']) if tree.selection() else None).pack(side='left')
        ttk.Button(actions,text='Apply Selected Suggestions',style='Primary.TButton',command=apply).pack(side='right')

    def visual_photo_review(self):
        if not self.require():return
        self.save()
        PhotoReviewWindow(self)

    def assign(self):
        slot=self.slot.get()
        if slot in PHASE.values() and self.selected_photo:
            stage=next(key for key,value in PHASE.items() if value==slot)
            if not messagebox.askyesno('Confirm Visible Conditions',CRITERIA[stage]+'\n\nHave you checked the visible condition in this photo? Do not rely on the filename or date alone.'):return
            try:
                self.save();apply_visual_stage(self.case,[self.selected_photo],stage,visually_checked=True)
                self.save();self.refresh_assignments()
            except Exception as exc:messagebox.showerror('Photo Review Failed',str(exc))
        else:super().assign()

    def draw_evidence(self):
        super().draw_evidence()
        if not self.case:return
        row=ttk.Frame(self.evidence_tab,padding=(0,0,0,10))
        row.pack(fill='x',before=self.evidence_tab.winfo_children()[0])
        ttk.Button(row,text='Review Container & Measurements',style='Primary.TButton',command=self.measurements).pack(side='left')
        ttk.Button(row,text='+ Add Load',command=self.add_load).pack(side='left',padx=8)
        ttk.Button(row,text='Visual Photo Review',command=self.visual_photo_review).pack(side='left')

    def measurements(self):
        self.save();index=int(self.e_load.get())-1;load=self.case['loads'][index]
        win=tk.Toplevel(self.root);win.title(f'Load {index+1} | Container & Measurements');win.geometry('650x610');win.transient(self.root);win.grab_set()
        body=ttk.Frame(win,padding=22);body.pack(fill='both',expand=True)
        ttk.Label(body,text=f'Load {index+1}: Confirm the Container',font=(self.ui_font,18,'bold')).pack(anchor='w')
        ttk.Label(body,text='Review the original photos. Enter only documented measurements. If the vendor did not supply them, leave them unresolved and request corrections.',wraplength=590).pack(anchor='w',pady=12)
        ttk.Button(body,text='Open Selected Source Photo',command=lambda:self.open_original(self.selected_photo)).pack(anchor='w',pady=(0,10))
        values={}
        advanced=ttk.Frame(body)
        for label,key,default in [('Container / Trailer Reference','container_name',''),('Length (ft)','length_ft',''),('Width (ft)','width_ft',''),('Wall Height (ft)','side_height_ft',''),('Final Fill (%)','fill_fraction','1'),('Uniform Overage Height (ft)','overage_height_ft','0'),('Separate Documented Overage (CYD)','overage_cyd','0'),('Overage Evidence / Note','overage_note','')]:
            parent=advanced if key in ('overage_height_ft','overage_cyd','overage_note') else body
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=41).pack(side='left')
            var=tk.StringVar(value=str(float(load.get(key,default))*100 if key=='fill_fraction' else load.get(key,default)));values[key]=var;ttk.Entry(row,textvariable=var,width=18).pack(side='left',fill='x',expand=True)
        def toggle_details():
            if advanced.winfo_manager():advanced.pack_forget()
            else:advanced.pack(fill='x',before=result)
        ttk.Button(body,text='Additional Measurement Details',command=toggle_details).pack(anchor='w',pady=5)
        result=ttk.Label(body,text='',foreground=ACCENT);result.pack(anchor='w',pady=10)
        def confirm(close=True):
            proposed=dict(load,**{key:value.get() for key,value in values.items()})
            try:
                proposed['fill_fraction']=str(float(values['fill_fraction'].get())/100)
                calculated=volume(proposed)
            except Exception as exc:messagebox.showwarning('Measurements Need Review',str(exc),parent=win);return False
            load.update(proposed);load['measurements_confirmed']=True;self.case['bid_review_confirmed']=False
            self.save();result.configure(text=f'Confirmed: {calculated["total"]:.2f} CYD')
            if close:win.destroy()
            return True
        row=ttk.Frame(body);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Open CalculatorSoup',command=lambda:self.calculator_help(index) if confirm(False) else None).pack(side='left')
        ttk.Button(row,text='Attach Screenshot',command=lambda:self.attach_calculator(index) if confirm(False) else None).pack(side='left',padx=8)
        ttk.Button(body,text='Confirm Measurements',style='Primary.TButton',command=confirm).pack(anchor='e',pady=12)

    def update_measurements(self):
        # The import-first workflow reviews measurements in a focused dialog.
        pass

    def draw_finance(self):
        super().draw_finance()
        if not self.case:return
        # Place the final rate and bid review above the invoice fields inside the scrolling page.
        canvas=next(child for child in self.finance_tab.winfo_children() if isinstance(child,tk.Canvas))
        content=canvas.nametowidget(canvas.itemcget(canvas.find_all()[0],'window'))
        first=content.winfo_children()[0]
        card=ttk.Frame(content,style='Card.TFrame',padding=20);card.pack(fill='x',pady=(0,14),before=first)
        ttk.Label(card,text='Lowest Bid & Final Rate',style='Section.TLabel').pack(anchor='w')
        row=ttk.Frame(card,style='Card.TFrame');row.pack(fill='x',pady=10)
        ttk.Label(row,text='Rate per CYD ($)',style='Card.TLabel').pack(side='left')
        var=tk.StringVar(value=str(self.case.get('rate_per_cyd','')));self.vars['rate_per_cyd']=var
        ttk.Entry(row,textvariable=var,width=16).pack(side='left',padx=12)
        bids=[d for d in self.case.get('package_documents',[]) if d.get('role')=='bid']
        ttk.Label(card,text='Each load is rounded to 2 decimal CYD before the total is priced.',style='Card.TLabel',foreground=MUTED,wraplength=590).pack(anchor='w')
        listing='\n'.join(f"{d.get('vendor') or d.get('name','Bid')}: ${d.get('amount') or 'Amount Needed'}" for d in bids) or 'No bids attached. Add and review bids in Import Files.'
        ttk.Label(card,text=listing,style='Card.TLabel',wraplength=590).pack(anchor='w',pady=8)
        ttk.Button(card,text='Confirm Lowest Received Bid',command=self.confirm_bids).pack(anchor='w')
        ttk.Button(card,text='Review Detected Invoice Values',command=self.use_invoice_values).pack(anchor='w',pady=(10,0))
        self.show_checks()

    def use_invoice_values(self):
        invoices=[item for item in self.case.get('package_documents',[]) if item.get('role')=='invoice']
        if len(invoices)!=1:
            messagebox.showinfo('Review Invoice Values','Automatic suggestions are offered for one invoice section at a time. Enter or reconcile multiple invoices manually.');return
        suggestions=invoices[0].get('cost_suggestions',{})
        if not suggestions:messagebox.showinfo('Manual Review Needed','No unambiguous labeled values could be read. Enter the invoice figures from the original.');return
        message='\n'.join(f'{key.replace("_"," ").title()}: {value}' for key,value in suggestions.items())
        if not messagebox.askyesno('Review Read Values',message+'\n\nApply these suggestions? Check them against the original invoice before confirming.'):return
        for key,value in suggestions.items():
            if key in self.vars:self.vars[key].set(value)
        if 'invoice_deduction_usd' in suggestions:
            self.vars['invoice_deduction_status'].set('yes');self.finance_displays['invoice_deduction_status'].set('Yes · separately deducted')
        self.case['bid_review_confirmed']=False;self.save();self.show_checks()

    def confirm_bids(self):
        self.save();bids=[d for d in self.case.get('package_documents',[]) if d.get('role')=='bid']
        try:
            if not bids or not all(d.get('confirmed') for d in bids):raise ValueError('Add and confirm every received bid in Import Files.')
            amounts=[number(d.get('amount')) for d in bids];value=totals(self.case)
            if value['gross']>min(amounts):raise ValueError('The measured total at this rate exceeds the lowest bid. Review the figures.')
        except Exception as exc:messagebox.showwarning('Review Bids',str(exc));return
        if messagebox.askyesno('Confirm Bid Review','Have all received bids been included, and does the selected vendor and rate represent the lowest bid? This confirmation is not COR approval.'):
            from cor_package import bid_fingerprint
            self.case['bid_review_confirmed']=True;self.case['bid_confirmation_hash']=bid_fingerprint(self.case);self.save();self.show_checks()

    def evaluate(self):
        qty,gross,ded,issues=super().evaluate()
        for problem in validate(self.case):issues.append('BLOCKING / '+problem)
        for problem in property_review_issues(self.case):issues.append('REVIEW / '+problem)
        for i,load in enumerate(self.case['loads'],1):
            if not load.get('measurements_confirmed'):issues.append(f'BLOCKING / Load {i} measurement: confirm the container dimensions and final fill.')
        return qty,gross,ded,list(dict.fromkeys(issues))

    def issue_step(self,issue):
        lower=issue.lower()
        if any(word in lower for word in ('document','vendor invoice.','vendor bid','cost estimate','page range','pdf','overlapping')):return 0
        if any(word in lower for word in ('calculator','measurement','photo','image','evidence','source audit','container','load ')):return 1
        return 2

    def draw_checks(self):
        if not self.case:self.empty(self.check_tab);return
        self.clear(self.check_tab)
        card=ttk.Frame(self.check_tab,style='Card.TFrame',padding=16);card.pack(fill='x',pady=(0,12))
        ttk.Label(card,text='Package Summary',style='Section.TLabel').pack(anchor='w')
        self.review_summary=ttk.Label(card,text='',style='Card.TLabel',wraplength=580,justify='left')
        self.review_summary.pack(anchor='w',pady=(8,0))
        self.review_count=ttk.Label(self.check_tab,text='',font=(self.ui_font,11,'bold'),wraplength=580)
        self.review_count.pack(anchor='w',pady=(0,8))
        actions=ttk.Frame(self.check_tab);actions.pack(fill='x',pady=(0,10))
        ttk.Button(actions,text='Go to Selected Step',command=self.resolve_issue).pack(side='left')
        ttk.Button(actions,text='Request Description',command=self.preview_description).pack(side='left',padx=7)
        ttk.Button(actions,text='Refresh',command=self.show_checks).pack(side='left')
        body=ttk.Frame(self.check_tab);body.pack(fill='both',expand=True)
        self.review_tree=ttk.Treeview(body,columns=('status','step'),show='tree headings',height=2)
        tree=self.review_tree
        for key,label,width in [('#0','What Needs Attention',380),('status','Action',70),('step','Where',115)]:
            tree.heading(key,text=label);tree.column(key,width=width,minwidth=80 if key=='#0' else 50,stretch=key=='#0')
        scroll=ttk.Scrollbar(body,command=tree.yview);scroll.pack(side='right',fill='y')
        horizontal=ttk.Scrollbar(body,orient='horizontal',command=tree.xview);horizontal.pack(side='bottom',fill='x')
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set);tree.pack(fill='both',expand=True)
        tree.bind('<Double-1>',lambda event:self.resolve_issue())
        self.show_checks()

    def preview_description(self):
        self.save()
        try:text=description(self.case)
        except Exception as exc:messagebox.showinfo('Complete Cost Review First',str(exc));return
        win=tk.Toplevel(self.root);win.title('COR Request Description');win.geometry('760x380')
        box=tk.Text(win,wrap='word',font=(self.ui_font,11),padx=20,pady=20);box.pack(fill='both',expand=True);box.insert('1.0',text)
        def copy():self.root.clipboard_clear();self.root.clipboard_append(text)
        ttk.Button(win,text='Copy Description',command=copy).pack(anchor='e',padx=20,pady=12)

    def generate(self):
        if not self.require():return
        self.save();issues=self.evaluate()[3]
        if issues and not messagebox.askyesno('Incomplete Package','Some items still need review. Export an incomplete draft with its checklist? Do not submit an incomplete draft to COR.'):return
        folder=self.case_dir/'output';folder.mkdir(exist_ok=True)
        try:
            report=assemble(self.case,folder/(safe(self.case['case_number'])+'_COR_PACKAGE_DRAFT.pdf'),issues)
            messagebox.showinfo('COR Draft Exported',f"{report['pages']} Pages Assembled\nStatus: {report['status']}\n\nUse Open Output Folder to find the PDF and review report. The request description is saved when all checks are resolved.")
            self.open_output()
        except Exception as exc:messagebox.showerror('Package Export Failed',str(exc))
