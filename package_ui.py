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
from local_photo_sorter import LocalPhotoSorterWindow
from visual_photo_review import PhotoReviewWindow, property_review_issues, apply_visual_stage, PHASE, CRITERIA
SLOT_LABELS.update({key: value.title().replace('Cyd', 'CYD').replace('Pdf', 'PDF') for key,value in SLOT_LABELS.items()})
SLOT_LABELS['financial_pdfs'] = 'Invoice / Financial Document'

guided_ui.STEPS[:] = [('Import Files', 'Start with the vendor files. No measurements or pricing required yet.'),
                     ('Review Loads', 'Match the photos, then confirm only the details that need your input.'),
                     ('Review Costs', 'Check the invoice figures, first-10 amount and lowest bid.'),
                     ('Create Package', 'Review the complete package and export one combined COR draft.')]

class PackageApp(GuidedApp):
    def __init__(self, root):
        self._case_temp=None;self._project_file=None;self._saved_project_fingerprint=None
        self.scan_cancel=threading.Event()
        self.scan_running = False
        super().__init__(root)
        root.title('ED Package Builder')
        self.status.set('Create a case with its case number and vendor, then import your files.')
        def add_load_text_tool(widget):
            if isinstance(widget,ttk.Menubutton):
                menu=widget.nametowidget(str(widget['menu']))
                menu.add_command(label='Review Load Text Suggestions',command=self.review_suggestions)
                menu.add_command(label='Read Imported Photo Text',command=self.scan_photos)
            if isinstance(widget,ttk.Button) and widget.cget('text')=='Save':widget.configure(text='Save Project',command=self.save_project)
            for child in widget.winfo_children():add_load_text_tool(child)
        add_load_text_tool(root)
        root.bind('<Control-s>',lambda event:self.save_project())

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

    def help(self):
        messagebox.showinfo('Using ED Package Builder','1. Import Files: add vendor photos, invoices and bids. Confirm each document purpose.\n\n2. Review Loads: group and select photos, match load evidence, then check container measurements and attach the cubic yard calculation.\n\n3. Review Costs: check the invoice figures, first-10 amount and lowest bid.\n\n4. Create Package: resolve missing items and export the combined PDF. Open Output Folder shows your saved files.\n\nSave Project keeps a portable file with your originals and progress. Open it to continue later. New cases use temporary working folders, removed when the session closes.')

    def save(self):
        super().save()
        if self.case and self._case_temp is not None:self.status.set('Temporary session · Use Save Project to keep your progress.')

    def save_project(self):
        if not self.require():return False
        if any(window.running for window in getattr(self,'_photo_sorting_windows',[])) or self.scan_running:
            messagebox.showinfo('Processing in Progress','Stop photo sorting and wait for the current photo or text reading to finish before saving the portable project.');return False
        from portable_project import export_project,fingerprint
        self.save()
        cache=self.case_dir/'local_photo_sorting.json'
        if cache.is_file():self.case['local_photo_results']=json.loads(cache.read_text(encoding='utf-8'))
        path=filedialog.asksaveasfilename(title='Save Project to Resume Later',defaultextension='.edcase',initialfile=self._project_file.name if self._project_file else safe(self.case['case_number'])+'.edcase',initialdir=str(self._project_file.parent) if self._project_file else str(Path.home()),filetypes=[('ED Project','*.edcase')])
        if not path:return False
        try:
            self.status.set('Saving project... Large photo sets may take a moment.');self.root.update_idletasks()
            export_project(self.case,self.case_dir,path)
            self._project_file=Path(path);self._saved_project_fingerprint=fingerprint(self.case,self.case_dir)
            self.status.set('Project saved: '+str(path));return True
        except Exception as exc:messagebox.showerror('Cannot Save Project',str(exc));return False

    def prepare_leave(self):
        if self.scan_running:
            self.scan_cancel.set();self.status.set('Stopping text reading after the current image. Try closing or changing cases again in a moment.');return False
        if any(window.running for window in getattr(self,'_photo_sorting_windows',[])):
            messagebox.showinfo('Processing in Progress','Stop photo sorting and wait for the current photo to finish before closing or changing cases.');return False
        if not self.case or self._case_temp is None:return True
        from portable_project import fingerprint
        self.save()
        if self._saved_project_fingerprint==fingerprint(self.case,self.case_dir):return True
        answer=messagebox.askyesnocancel('Save This Project?','Save this project so you can resume later?\n\nYes: choose where to save the project.\nNo: discard this temporary session.\nCancel: keep working.')
        if answer is None:return False
        if answer and not self.save_project():return False
        return True

    def release_temporary_case(self):
        for window in getattr(self,'_photo_sorting_windows',[]):
            if not window.closed:window.close()
        if self._case_temp is not None:self._case_temp.cleanup();self._case_temp=None

    def open_case(self):
        import tempfile
        from portable_project import import_project,fingerprint
        path=filedialog.askopenfilename(title='Open Project',filetypes=[('ED Project','*.edcase'),('Older Case','case.json')])
        if not path:return
        if not self.prepare_leave():return
        owner=None
        try:
            self.status.set('Opening project...');self.root.update_idletasks()
            if Path(path).suffix.lower()=='.edcase':
                owner=tempfile.TemporaryDirectory(prefix='ed-project-');directory=Path(owner.name);case=import_project(path,directory)
            else:directory=Path(path).parent;case=json.loads(Path(path).read_text(encoding='utf-8'))
            self.release_temporary_case();self.case=case;self.case_dir=directory;self._case_temp=owner
            self._project_file=Path(path) if owner else None;self.vars={};self.refresh();self.go(0)
            self._saved_project_fingerprint=fingerprint(self.case,self.case_dir) if owner else None
            if owner:self.status.set('Project opened · Temporary session. Use Save Project to keep changes.')
        except Exception as exc:
            if owner:owner.cleanup()
            messagebox.showerror('Cannot Open Project',str(exc))

    def close_app(self):
        if not self.prepare_leave():return
        if self.case:self.save()
        self.release_temporary_case();self.root.destroy()
        from small_vision_runtime import RUNTIME
        RUNTIME.stop()

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
            if not self.prepare_leave():return
            import tempfile
            self.release_temporary_case();self._case_temp=tempfile.TemporaryDirectory(prefix='ed-project-');directory=Path(self._case_temp.name)
            self._project_file=None;self._saved_project_fingerprint=None
            self.case=make_case(case,'',vendor,1,'');self.case['verified_first_10_amount']=''
            self.case_dir=directory;self.vars={};self.save();self.refresh();self.go(0);win.destroy()
        ttk.Button(body,text='Create Case',style='Primary.TButton',command=create).pack(anchor='e',pady=22)

    def draw_case(self):
        if not self.case:self.empty(self.case_tab);return
        self.clear(self.case_tab)
        header=self.card(self.case_tab,'Import the Vendor Files','Import the folder or ZIP you received. The app keeps the originals and prepares document suggestions for review.')
        row=ttk.Frame(header,style='Card.TFrame');row.pack(fill='x',pady=6)
        ttk.Button(row,text='Import Folder',style='Primary.TButton',command=self.import_files).pack(side='left')
        ttk.Button(row,text='Import ZIPs',command=self.import_zips).pack(side='left',padx=8)
        ttk.Button(row,text='Organize Photos Locally',command=self.local_ai_review).pack(side='left')
        count=len(self.case.get('imported_files',[]))
        storage_mb=sum(Path(r['path']).stat().st_size for r in self.case.get('imported_files',[]) if Path(r['path']).is_file())/1_000_000
        ttk.Label(header,text=f'{count} Files Imported  ·  {storage_mb:.0f} MB  ·  {len(self.case["loads"])} Load(s)',style='Card.TLabel',foreground=ACCENT).pack(anchor='w',pady=(12,0))
        ttk.Label(self.case_tab,text='Package Documents',font=(self.ui_font,13,'bold')).pack(anchor='w',pady=(0,6))
        ttk.Label(self.case_tab,text='Add invoices and bids as images or PDFs. Open a row to confirm its purpose. PDF sections can use page ranges.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=(0,10))
        actions=ttk.Frame(self.case_tab);actions.pack(side='bottom',fill='x',pady=12)
        ttk.Button(actions,text='Review Document',command=self.edit_document).pack(side='left')
        ttk.Button(actions,text='Add Document',command=self.add_document).pack(side='left',padx=8)
        ttk.Button(actions,text='Add Bid',command=self.add_bid).pack(side='left',padx=(0,8))
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
        # Bulk OCR is explicit; importing thousands of photos does not start a second full scan.

    def add_bid(self):
        self.add_document(purpose='bid')

    def add_document(self,purpose=None):
        if not self.require():return
        paths=filedialog.askopenfilenames(title='Add Bid Files' if purpose=='bid' else 'Add Invoices, Bids or Supporting Documents',filetypes=[('Images and Documents','*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.docx')])
        if not paths:return
        digests={hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
        self._import_paths([Path(p) for p in paths])
        indices=[]
        for record in self.case.get('imported_files',[]):
            if record.get('sha256') in digests:indices.append(self.register_document(record['path']))
        if purpose=='bid':
            for index in indices:
                item=self.case['package_documents'][index]
                item.update(role='bid',confirmed=False)
                if not item.get('debris_quantity_cyd'):item['debris_quantity_cyd']=item.get('cost_suggestions',{}).get('invoice_quantity_cyd','')
        self.save();self.draw_case()
        if len(indices)==1:
            self.documents.selection_set(str(indices[0]));self.edit_document()
        self.status.set('Documents Added. Confirm each document purpose before export.')
        images=[r for r in self.case.get('imported_files',[]) if r.get('sha256') in digests and Path(r['path']).suffix.lower() in IMAGE_EXT]
        if images:self.scan_photos(images)

    def register_document(self,path):
        documents=self.case.setdefault('package_documents',[])
        for index,record in enumerate(documents):
            if record['path']==path:return index
        source=next((r for r in self.case.get('imported_files',[]) if r['path']==path),dict(path=path,name=Path(path).name))
        records=document_suggestions(source)
        index=len(documents);documents.extend(records)
        self.case['bid_review_confirmed']=False
        return index

    def edit_document(self):
        from cor_package import apply_document_text_suggestions
        apply_document_text_suggestions(self.case)
        selected=self.documents.selection()
        if not selected:messagebox.showinfo('Select a Document','Select a document row first.');return
        index=int(selected[0]);item=self.case['package_documents'][index]
        win=tk.Toplevel(self.root);win.title('Review Package Document');win.geometry('640x560');win.transient(self.root);win.grab_set()
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
        bid_fields_end=row
        quantity_row=ttk.Frame(body)
        ttk.Label(quantity_row,text='Debris Quantity on Bid (CYD)',width=31).pack(side='left')
        values['debris_quantity_cyd']=tk.StringVar(value=item.get('debris_quantity_cyd',''))
        ttk.Entry(quantity_row,textvariable=values['debris_quantity_cyd']).pack(side='left',fill='x',expand=True)
        def show_bid_quantity(*args):
            if role.get()==ROLES['bid']:quantity_row.pack(fill='x',pady=7,after=bid_fields_end)
            else:quantity_row.pack_forget()
        role.trace_add('write',show_bid_quantity);show_bid_quantity()
        def confirm(split=False):
            record=dict(item,role=next(key for key,value in ROLES.items() if value==role.get()),confirmed=True,**{key:value.get().strip() for key,value in values.items()})
            try:
                import fitz
                from cor_package import parse_pages
                if Path(record['path']).suffix.lower()=='.pdf':
                    with fitz.open(record['path']) as source:parse_pages(record.get('pages'),len(source))
                if record['role']=='bid':
                    number(record['amount'])
                    if number(record['debris_quantity_cyd'])<=0:raise ValueError('Enter the debris quantity shown on this bid.')
            except Exception as exc:messagebox.showwarning('Check Document Details',str(exc),parent=win);return
            if split:self.case['package_documents'].append(record)
            else:self.case['package_documents'][index]=record
            self.case['bid_review_confirmed']=False;self.save();self.draw_case();win.destroy()
        row=ttk.Frame(body);row.pack(fill='x',pady=20)
        ttk.Button(row,text='Add as Another Section',command=lambda:confirm(True)).pack(side='left')
        ttk.Button(row,text='Confirm Document',style='Primary.TButton',command=confirm).pack(side='right')

    def scan_photos(self,records=None,review_when_done=False,on_complete=None):
        if not self.require() or self.scan_running:return
        self.scan_cancel.clear()
        self.save();records=list(records if records is not None else self.case.get('imported_files',[]));case_dir=self.case_dir
        cache=dict(self.case.get('photo_text_cache',{}))
        self.scan_running=True;results=queue.Queue();self.status.set('Reading Photo Text Locally... You can continue working.')
        def work():
            rows=[];notes=[]
            for item in records:
                if self.scan_cancel.is_set():break
                if Path(item['path']).suffix.lower() not in IMAGE_EXT:continue
                from calculator_evidence import file_digest
                try:digest=file_digest(item['path'])
                except OSError:
                    notes.append('A source file is unavailable.');continue
                cached=cache.get(item['path'])
                if cached and cached.get('sha256')==digest:
                    text,error=cached.get('text',''),cached.get('error','')
                else:
                    text,error=read_image(item['path'])
                    try:unchanged=file_digest(item['path'])==digest
                    except OSError:unchanged=False
                    if not unchanged:
                        notes.append('A source file changed during text reading. Run it again.');continue
                    cache[item['path']]=dict(sha256=digest,text=text,error=error)
                row=photo_suggestion(item,text);row['reader_note']=error;row['sha256']=digest
                rows.append(row)
                if error:notes.append(error)
            results.put((rows,notes))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            if results.empty():self.root.after(150,poll);return
            rows,notes=results.get();self.scan_running=False
            if self.case_dir!=case_dir:return
            self.case['photo_suggestions']=rows;self.case['photo_text_cache']=cache
            from cor_package import apply_document_text_suggestions
            apply_document_text_suggestions(self.case);self.save()
            if self.current_step()==0:self.draw_case()
            if self.current_step()==2:self.draw_finance()
            self.status.set('Photo Reading Complete. Open Visual Photo Review to inspect conditions and date clues.' if not notes else 'Some text could not be read. Visual Photo Review remains available; date-only photos are usable.')
            if review_when_done:self.review_suggestions()
            if on_complete:on_complete()
            # Reading text never assigns the property stage or interrupts work with a popup.
        self.root.after(150,poll)

    def review_suggestions(self):
        if not self.require():return
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        rows=current_photo_suggestions(self.case)
        if not rows:
            messagebox.showinfo('No Clear Photo Text','No current, readable load or measurement suggestions are available. Read a selected photo or review it manually.');return
        win=tk.Toplevel(self.root);win.title('Review Photo Suggestions');win.geometry('980x560');win.transient(self.root)
        body=ttk.Frame(win,padding=20);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Suggestions Need Your Review',font=(self.ui_font,17,'bold')).pack(anchor='w')
        ttk.Label(body,text='Select rows you have checked. Only labeled measurements are suggested; unreadable tape measures require manual input.',wraplength=740).pack(anchor='w',pady=10)
        actions=ttk.Frame(body);actions.pack(side='bottom',fill='x',pady=(12,0))
        tree=ttk.Treeview(body,columns=('load','purpose','dimensions'),show='tree headings',selectmode='extended')
        for key,label,width in [('#0','File',240),('load','Load',55),('purpose','Photo Purpose',170),('dimensions','Measurements',320)]:tree.heading(key,text=label);tree.column(key,width=width,minwidth=40)
        tree.pack(fill='both',expand=True)
        for i,row in enumerate(rows):
            dimension_labels={'length_ft':'Length','width_ft':'Width','side_height_ft':'Height'}
            dims=', '.join(f'{dimension_labels[key]}: {value} ft' for key,value in row['dimensions'].items())
            tree.insert('','end',iid=str(i),text=row['name'],values=(row.get('load') or 'Unclear',SLOT_LABELS.get(row.get('slot'),'Review Manually'),dims))
        def apply():
            selected=tree.selection()
            if not selected:return
            if not messagebox.askyesno('Apply Reviewed Suggestions','Have you checked these photos and their load numbers? Existing assignments and entered measurements will not be overwritten.',parent=win):return
            self.save()
            try:
                changed=apply_photo_suggestions(self.case,[rows[int(ident)] for ident in selected])
                if not changed:
                    messagebox.showinfo('No Measurement or Stage Read','These photos identify a load but contain no clear measurement or progression-stage suggestion. Assign the photos manually.',parent=win);return
            except (ValueError,OSError) as exc:
                messagebox.showwarning('Review Source Photos',str(exc),parent=win);return
            self.save();self.refresh();win.destroy();self.go(1)
        ttk.Button(actions,text='Open Selected Photo',command=lambda:self.open_original(rows[int(tree.selection()[0])]['path']) if tree.selection() else None).pack(side='left')
        ttk.Button(actions,text='Apply Selected Suggestions',style='Primary.TButton',command=apply).pack(side='right')

    def local_ai_review(self):
        if not self.require():return
        for window in getattr(self,'_photo_sorting_windows',[]):
            if not window.closed:window.win.lift();return
        self.save();LocalPhotoSorterWindow(self)

    def visual_photo_review(self):
        if not self.require():return
        self.save()
        PhotoReviewWindow(self)

    def template_photo_review(self):
        if not self.require():return
        existing=getattr(self,'_template_review',None)
        if existing and not existing.closed and existing.win.winfo_exists():existing.win.lift();return
        from template_review import TemplateReviewWindow
        self.save();self._template_review=TemplateReviewWindow(self)

    def assign(self):
        slot=self.slot.get()
        if slot=='financial_pdfs' and self.selected_photo:
            try:
                if Path(self.selected_photo).suffix.lower() not in IMAGE_EXT|{'.pdf'}:
                    raise ValueError('Choose an image or PDF for this document.')
                self.save();index=self.register_document(self.selected_photo)
                self.save();self.go(0);self.draw_case()
                self.documents.selection_set(str(index));self.edit_document()
            except Exception as exc:messagebox.showerror('Cannot Add Document',str(exc))
            return
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
        ttk.Button(row,text='Review Suggested Photos',style='Primary.TButton',command=self.template_photo_review).pack(side='left')
        ttk.Button(row,text='Container Details',command=self.measurements).pack(side='left',padx=8)
        ttk.Button(row,text='+ Add Load',command=self.add_load).pack(side='left',padx=8)
        ttk.Button(row,text='All Photos',command=self.visual_photo_review).pack(side='left')
        ttk.Label(self.evidence_tab,text='Choose the clearest photo for each template slot. Use other views to verify measurements; supporting measurement photos are optional.',wraplength=780,style='Muted.TLabel').pack(fill='x',before=self.evidence_tab.winfo_children()[1],pady=(0,8))

    def measurements(self):
        self.save();index=int(self.e_load.get())-1;load=self.case['loads'][index]
        win=tk.Toplevel(self.root);win.title(f'Load {index+1} | Container & Measurements');win.geometry('650x610');win.transient(self.root);win.grab_set()
        body=self.scroll_page(win);body.configure(padding=22)
        ttk.Label(body,text=f'Load {index+1}: Confirm the Container',font=(self.ui_font,18,'bold')).pack(anchor='w')
        ttk.Label(body,text='Use photographed load cards and tape measurements. Invoice typing does not override the photos. Resolve conflicting photo measurements before confirming; leave unsupported dimensions blank.',wraplength=590).pack(anchor='w',pady=12)
        ttk.Button(body,text='Open Selected Source Photo',command=lambda:self.open_original(self.selected_photo)).pack(anchor='w',pady=(0,10))
        def read_selected():
            record=next((r for r in self.case.get('imported_files',[]) if r['path']==self.selected_photo),None)
            if not record:messagebox.showinfo('Select a Photo','Close this window and select a load-card photo in the imported-file list.',parent=win);return
            win.destroy();self.scan_photos([record],review_when_done=True)
        ttk.Button(body,text='Read Selected Photo Text',command=read_selected).pack(anchor='w',pady=(0,10))
        values={}
        advanced=ttk.Frame(body)
        supporting=tk.BooleanVar(value=bool(load.get('include_supporting_measurements',False)))
        for label,key,default in [('Container / Trailer Reference','container_name',''),('Length (ft)','length_ft',''),('Width (ft)','width_ft',''),('Wall Height (ft)','side_height_ft',''),('Final Fill (%)','fill_fraction','1'),('Uniform Overage Height (ft)','overage_height_ft','0'),('Separate Documented Overage (CYD)','overage_cyd','0'),('Overage Evidence / Note','overage_note','')]:
            parent=advanced if key in ('overage_height_ft','overage_cyd','overage_note') else body
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=41).pack(side='left')
            var=tk.StringVar(value=str(float(load.get(key,default))*100 if key=='fill_fraction' else load.get(key,default)));values[key]=var;ttk.Entry(row,textvariable=var,width=18).pack(side='left',fill='x',expand=True)
        ttk.Checkbutton(advanced,text='Include Supporting Measurement Photos in Package',variable=supporting).pack(anchor='w',pady=5)
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
            load.update(proposed);load['include_supporting_measurements']=supporting.get();load['measurements_confirmed']=True;self.case['bid_review_confirmed']=False
            self.save();result.configure(text=f'Confirmed: {calculated["total"]:.2f} CYD')
            if close:win.destroy()
            return True
        row=ttk.Frame(body);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Open Cubic Yard Calculation',command=lambda:self.calculator_help(index) if confirm(False) else None).pack(side='left')
        ttk.Button(row,text='Attach Calculation',command=lambda:self.attach_calculator(index) if confirm(False) else None).pack(side='left',padx=8)
        ttk.Button(body,text='Confirm Measurements',style='Primary.TButton',command=confirm).pack(anchor='e',pady=12)

    def update_measurements(self):
        # The import-first workflow reviews measurements in a focused dialog.
        tool=getattr(self,'_template_review',None)
        if tool and not tool.closed and tool.case is self.case and tool.win.winfo_exists():
            tool.refresh_tree();tool.render()

    def draw_finance(self):
        if not self.case:self.empty(self.finance_tab);return
        from cor_package import extract_costs
        # Readable suggestions are populated once; entered values are never overwritten.
        invoices=[d for d in self.case.get('package_documents',[]) if d.get('role')=='invoice']
        suggestions={}
        if len(invoices)==1:
            invoice=invoices[0];suggestions=dict(invoice.get('cost_suggestions',{}))
            cached=self.case.get('photo_text_cache',{}).get(invoice['path'],{})
            if cached.get('text'):
                from calculator_evidence import file_digest
                if cached.get('sha256')==file_digest(invoice['path']):suggestions.update(extract_costs(cached['text']))
            for key,value in suggestions.items():
                if self.case.get(key) in ('',None):self.case[key]=value
        content=self.scroll_page(self.finance_tab);self.finance_displays={}
        card=self.card(content,'1. Check the Invoice','Figures read from the invoice are suggestions. Compare them with the original and correct anything that is wrong.')
        if invoices:ttk.Button(card,text='Open Invoice',command=lambda:self.open_original(invoices[0]['path'])).pack(anchor='w',pady=(0,8))
        ttk.Label(card,text='Invoice figures found — please check them.' if suggestions else 'Enter any figures the app could not read.',style='Card.TLabel',foreground=MUTED).pack(anchor='w')
        grid=ttk.Frame(card,style='Card.TFrame');grid.pack(fill='x',pady=8)
        for i,(label,key) in enumerate([('Cubic Yards on Invoice','invoice_quantity_cyd'),('Invoice Total ($)','invoice_amount_usd'),('HUD Request Rate ($/CYD)','rate_per_cyd')]):
            self.field(grid,label,key,self.case.get(key,''),i//2,i%2)
        card=self.card(content,'2. Initial Services')
        def choice(parent,label,key,choices):
            ttk.Label(parent,text=label,style='Card.TLabel',wraplength=580).pack(anchor='w',pady=(10,4))
            raw=tk.StringVar(value=self.case.get(key,'unknown'));self.vars[key]=raw
            display=tk.StringVar(value=next((name for name,value in choices if value==raw.get()),choices[0][0]));self.finance_displays[key]=display
            box=ttk.Combobox(parent,textvariable=display,values=[name for name,_ in choices],state='readonly',width=48);box.pack(anchor='w')
            box.bind('<<ComboboxSelected>>',lambda event:raw.set(dict(choices)[display.get()]))
        choice(card,'Are the First 10 CYD (Initial Services) Deducted From the Invoice?', 'invoice_deduction_status', [('Choose an Answer','unknown'),('Yes','yes'),('No','no')])
        question_box=card.winfo_children()[-1]
        self.initial_services_question=tk.StringVar(value='HUD Deduction for the First 10 CYD')
        ttk.Label(card,textvariable=self.initial_services_question,style='Card.TLabel').pack(anchor='w',pady=(12,4))
        self.vars['verified_first_10_amount']=tk.StringVar(value='')
        self.hud_deduction_display=tk.StringVar()
        ttk.Label(card,textvariable=self.hud_deduction_display,style='Card.TLabel',font=(self.ui_font,12,'bold')).pack(anchor='w',pady=(0,8))
        deduction_row=ttk.Frame(card,style='Card.TFrame')
        self.field(deduction_row,'Deduction on Invoice ($)','invoice_deduction_usd',self.case.get('invoice_deduction_usd',''),0,0)
        def initial_services_changed(*args):
            # This value is calculated, never an editable vendor bookkeeping credit.
            proposed=dict(self.case,rate_per_cyd=self.vars['rate_per_cyd'].get())
            try:
                value=totals(proposed);amount=str(value['allowance'])
                self.hud_deduction_display.set(f"{min(value['quantity'],number('10')):g} CYD × ${value['rate']:,.2f} = ${value['allowance']:,.2f}")
            except (ValueError,KeyError):
                amount='';self.hud_deduction_display.set('Confirm the load measurements and request rate.')
            if self.vars['verified_first_10_amount'].get()!=amount:self.vars['verified_first_10_amount'].set(amount)
            answer=self.vars['invoice_deduction_status'].get();shown=self.vars['invoice_deduction_usd'].get()
            if answer=='yes' or (answer=='no' and shown.strip() not in ('','0','0.00')):deduction_row.pack(fill='x')
            else:deduction_row.pack_forget()
        self.vars['invoice_deduction_status'].trace_add('write',initial_services_changed)
        self.vars['rate_per_cyd'].trace_add('write',initial_services_changed)
        initial_services_changed()
        details=ttk.Frame(card,style='Card.TFrame')
        self.invoice_details_frame=details
        def toggle_details():
            if details.winfo_manager():details.pack_forget()
            else:details.pack(fill='x',before=confirm_button)
        ttk.Button(card,text='Other Invoice Details',command=toggle_details).pack(anchor='w',pady=(12,4))
        choice(details,'Does the invoice list all removed cubic yards?', 'invoice_quantity_basis', [('Choose an Answer','unknown'),('Yes, Including the First 10','includes'),('No, It Leaves Out the First 10','excludes')])
        self.vars['first_10_prior_work']=tk.StringVar(value='no')
        grid=ttk.Frame(details,style='Card.TFrame');grid.pack(fill='x',pady=8)
        self.field(grid,'Invoice Reconciliation Notes','financial_confirmation_note',self.case.get('financial_confirmation_note',''),0,0)
        confirm_button=ttk.Button(card,text='Confirm Invoice Details',style='Primary.TButton',command=self.confirm_financial_rule);confirm_button.pack(anchor='w',pady=8)
        from cor_package import required_bid_count
        count=required_bid_count(self.case)
        card=self.card(content,'3. Compare Bids',f'{count} bid(s) required for this amount. Include the debris quantity on each bid.' if count else 'Confirm the applicable amount basis / bid requirement for this case.')
        ttk.Button(card,text='Add Bid — Image or PDF',command=lambda:(self.go(0),self.add_bid())).pack(anchor='w',pady=(0,8))
        bids=[d for d in self.case.get('package_documents',[]) if d.get('role')=='bid']
        def bid_sort(d):
            try:return number(d.get('amount'))
            except ValueError:return number('999999999')
        ordered=sorted(bids,key=bid_sort)
        listing='\n'.join(('Lowest Received: ' if i==0 else '')+f"{d.get('vendor') or d.get('name','Bid')}: ${d.get('amount') or 'Amount Needed'}" for i,d in enumerate(ordered)) or 'No bids attached yet.'
        ttk.Label(card,text=listing,style='Card.TLabel',wraplength=580).pack(anchor='w',pady=8)
        ttk.Button(card,text='Confirm Lowest Bid',command=self.confirm_bids).pack(anchor='w')
        card=self.card(content,'Amount to Request')
        self.finance_summary=ttk.Label(card,text='',style='Card.TLabel',wraplength=600,justify='left');self.finance_summary.pack(anchor='w',pady=8)
        ttk.Button(card,text='Update Total',command=lambda:(self.save(),self.show_checks())).pack(anchor='w')
        self.show_checks()

    def finance_fingerprint(self):
        from cor_package import financial_fingerprint
        return financial_fingerprint(self.case)

    def confirm_financial_rule(self):
        self.sync_case()
        try:
            value=totals(self.case);status=self.case.get('invoice_deduction_status')
            if value['rate']<=0:raise ValueError('Enter the applicable HUD request rate.')
            if status not in ('yes','no'):raise ValueError('Choose Yes or No for the Initial Services question.')
            billed=number(self.case.get('invoice_quantity_cyd'));number(self.case.get('invoice_amount_usd'))
            shown=self.case.get('invoice_deduction_usd','')
            if status=='yes':
                if not str(shown).strip():raise ValueError('Enter the actual deduction printed on the invoice.')
                if number(shown)!=value['allowance']:raise ValueError('The invoice deduction differs from 10 CYD at the request rate. Reconcile the invoice before confirming.')
            elif str(shown).strip() and number(shown)!=0:raise ValueError('The invoice has a deduction entered, but No is selected. Check the original invoice.')
            if self.case.get('invoice_quantity_basis','unknown')=='unknown':
                if abs(value['quantity']-billed)<=number('.02'):basis='includes'
                elif abs(value['request_quantity']-billed)<=number('.02'):basis='excludes'
                else:raise ValueError('The invoice quantity differs from the photo-supported measurements. Reconcile the invoice.')
            else:basis=self.case['invoice_quantity_basis']
        except ValueError as exc:
            self.invoice_details_frame.pack(fill='x');messagebox.showwarning('Check Invoice Details',str(exc));return
        if not messagebox.askyesno('Confirm Invoice Details','Have you checked the invoice, the photo-supported quantity, and the calculated first-10-CYD deduction at the request rate?'):return
        self.vars['invoice_quantity_basis'].set(basis)
        self.vars['first_10_prior_work'].set('no')
        self.vars['verified_first_10_amount'].set(str(value['allowance']))
        if status=='no':self.vars['invoice_deduction_usd'].set('0')
        self.sync_case()
        if not self.case.get('financial_confirmation_note','').strip():self.case['financial_confirmation_note']='HUD deduction calculated at the request rate; invoice treatment checked.'
        self.vars['financial_confirmation_note'].set(self.case['financial_confirmation_note'])
        self.case['financial_confirmation_hash']=self.finance_fingerprint();self.save();self.show_checks()

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
            from cor_package import bid_requirements
            bid_issues=bid_requirements(self.case)
            if bid_issues:raise ValueError('\n'.join(bid_issues))
            if not bids or not all(d.get('confirmed') for d in bids):raise ValueError('Add and confirm every received bid in Import Files.')
            amounts=[number(d.get('amount')) for d in bids];value=totals(self.case)
            if value['gross']>min(amounts):raise ValueError('The measured total at this rate exceeds the lowest bid. Review the figures.')
        except Exception as exc:messagebox.showwarning('Review Bids',str(exc));return
        if messagebox.askyesno('Confirm Bid Review','Have all received bids been included, and does the selected vendor and rate represent the lowest bid? '):
            from cor_package import bid_fingerprint
            self.case['bid_review_confirmed']=True;self.case['bid_confirmation_hash']=bid_fingerprint(self.case);self.save();self.show_checks()

    def evaluate(self):
        qty,gross,ded,issues=super().evaluate()
        # Preserve legacy evidence/source audits; use current rules for money.
        issues=[issue for issue in issues if ('Source audit:' in issue or re.match(r'^(?:BLOCKING / )?Load \d',issue) or 'First 10 CYD progression' in issue or 'Missing property before' in issue)]
        try:
            value=totals(self.case);qty=float(value['quantity']);gross=float(value['gross']);ded=float(value['allowance'])
        except (ValueError,KeyError):ded=None
        for problem in validate(self.case):issues.append('BLOCKING / '+problem)
        for problem in property_review_issues(self.case):issues.append('REVIEW / '+problem)
        for i,load in enumerate(self.case['loads'],1):
            if not load.get('measurements_confirmed'):issues.append(f'BLOCKING / Load {i} measurement: confirm the container dimensions and final fill.')
        return qty,gross,ded,list(dict.fromkeys(issue.replace('CalculatorSoup screenshot','cubic yard calculation').replace('CalculatorSoup','Cubic Yard Calculation') for issue in issues))

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
        if issues and not messagebox.askyesno('Incomplete Package','Some items still need review. Export the available documents anyway? Missing items remain listed in the app and will not be printed in the PDF.'):return
        destination=None
        if self._case_temp is not None:
            destination=filedialog.asksaveasfilename(title='Save COR Package',defaultextension='.pdf',initialfile=safe(self.case['case_number'])+'_COR_Package.pdf',filetypes=[('PDF','*.pdf')])
            if not destination:return
            if Path(destination).resolve().is_relative_to(self.case_dir.resolve()):
                messagebox.showwarning('Choose a Saved Location','Choose a folder outside the temporary workspace so the exported PDF stays saved.');return
        folder=self.case_dir/'output';folder.mkdir(exist_ok=True)
        try:
            report=assemble(self.case,folder/(safe(self.case['case_number'])+'_COR_PACKAGE_DRAFT.pdf'),issues)
            if destination:
                from portable_project import atomic_copy
                atomic_copy(folder/(safe(self.case['case_number'])+'_COR_PACKAGE_DRAFT.pdf'),destination)
                text=folder/'COR_Request_Description.txt'
                if text.is_file():atomic_copy(text,Path(destination).with_suffix('.description.txt'))
                self.status.set('Package saved: '+str(destination))
            messagebox.showinfo('Package Exported',f"{report['pages']} Pages Assembled\nStatus: {report['status']}\n\nUse Open Output Folder to find the PDF and review report. The request description is saved when all checks are resolved.")
            if not destination:self.open_output()
        except Exception as exc:messagebox.showerror('Package Export Failed',str(exc))
