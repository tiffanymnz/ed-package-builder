from ui_windows import fit_window
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
                     ('Create Package', 'Review the complete package and export one combined COR package.')]

class PackageApp(GuidedApp):
    def __init__(self, root):
        self._background_photos=None;self._deferred_project_save=False
        self._case_temp=None;self._project_file=None;self._saved_project_fingerprint=None
        self.scan_cancel=threading.Event()
        self.scan_running = False
        super().__init__(root)
        root.title('ED Package Builder');fit_window(root,root,(1180,800),(900,640))
        self.status.set('Create a case with its case number and vendor, then import your files.')
        def add_load_text_tool(widget):
            if isinstance(widget,ttk.Menubutton):
                menu=widget.nametowidget(str(widget['menu']))
                menu.delete(0,'end')
                menu.add_command(label='Package Overview',command=self.package_overview)
                menu.add_command(label='Review Load Cards',command=self.review_load_cards)
                menu.add_command(label='Organize Photos',command=self.organize_photos)
                menu.add_command(label='Fill Template',command=self.template_photo_review)
                menu.add_command(label='Recover Interrupted Export',command=self.recover_export)
                menu.add_command(label='Storage and Performance',command=self.performance_check)
                advanced=tk.Menu(menu,tearoff=False)
                advanced.add_command(label='Detailed Photo Review',command=self.visual_photo_review)
                advanced.add_command(label='Text Suggestions',command=self.review_suggestions)
                advanced.add_command(label='Photo Sorting Setup',command=self.local_ai_review)
                advanced.add_command(label='Audit Source Files',command=self.audit_evidence)
                menu.add_cascade(label='Advanced',menu=advanced)
                menu.add_separator();menu.add_command(label='How to Use',command=self.help)
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
        for control in (self.next_button,self.project_save_button,self.output_button):control.configure(state='normal' if self.case else 'disabled')
        if self.current_step()==1:self.refresh_load_progress()
        if self.current_step()==3: self.next_button.configure(text='Export COR Package')

    def refresh_load_progress(self):
        tree=getattr(self,'load_progress',None)
        if not self.case or tree is None or not tree.winfo_exists():return
        from workflow_status import package_inventory
        for row in package_inventory(self.case):
            if row['kind']=='template' and tree.exists(str(row['load'])):tree.item(str(row['load']),values=(row['detail'],))

    def open_original(self,path):
        if not path:messagebox.showinfo('Select a Photo','Select a source photo first.');return
        import os,sys,subprocess
        try:
            if sys.platform=='win32':os.startfile(str(path))
            else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)])
        except Exception as exc:messagebox.showerror('Cannot Open Source',str(exc))

    def empty(self,tab):
        self.clear(tab)
        card=self.card(tab,'Start Your ED Package','Create a case with the case number and vendor, then import the folder or ZIP you received. Review the documents, loads and costs before exporting your package.')
        ttk.Button(card,text='Create Case',style='Primary.TButton',command=self.new_case).pack(anchor='w',pady=(12,8))
        ttk.Button(card,text='Open Project',command=self.open_case).pack(anchor='w')

    def help(self):
        messagebox.showinfo('Using ED Package Builder','1. Import Files: add vendor photos, invoices and bids. Confirm each document purpose.\n\n2. Review Loads: group and select photos, match load evidence, then check container measurements and attach the cubic yard calculation.\n\n3. Review Costs: check the invoice figures, first-10 amount and lowest bid.\n\n4. Create Package: resolve missing items and export the combined PDF. Open Output Folder shows your saved files.\n\nSave Project keeps a portable file with your originals and progress. Open it to continue later. New cases use temporary working folders, removed when the session closes.')

    def save(self):
        super().save()
        if self.case and self._case_temp is not None:self.status.set('Temporary session · Use Save Project to keep your progress.')

    def finish_photo_work(self,action):
        service=self._background_photos
        if not ((service and service.case is self.case and service.running) or self.scan_running):return False
        if service:service.cancel.set()
        self.scan_cancel.set();self.status.set('Finishing the current photo, then continuing...')
        if not self._deferred_project_save:
            self._deferred_project_save=True;case=self.case
            def finish():
                if self.case is not case:self._deferred_project_save=False;return
                if (service and service.running) or self.scan_running:self.root.after(200,finish);return
                self._deferred_project_save=False;action()
                if action==self.save_project and self.case is case:self.start_photo_work()
            self.root.after(200,finish)
        return True

    def save_project(self):
        if getattr(self,'_file_task_running',False):return False
        if not self.require():return False
        if self.finish_photo_work(self.save_project):return False
        if any(window.running for window in getattr(self,'_photo_sorting_windows',[])) or self.scan_running:
            messagebox.showinfo('Processing in Progress','Stop photo sorting and wait for the current photo or text reading to finish before saving the portable project.');return False
        try:
            from portable_project import export_project,fingerprint,photo_cache
            self.save()
            cache=self.case_dir/'local_photo_sorting.json'
            if cache.is_file():self.case['local_photo_results']=photo_cache(self.case,self.case_dir)
            path=filedialog.asksaveasfilename(title='Save Project to Resume Later',defaultextension='.edcase',initialfile=self._project_file.name if self._project_file else safe(self.case['case_number'])+'.edcase',initialdir=str(self._project_file.parent) if self._project_file else str(Path.home()),filetypes=[('ED Project','*.edcase')])
            if not path:return False
            try:
                self.status.set('Saving project... Large photo sets may take a moment.');self.root.update_idletasks()
                from background_task import run_file_task
                self._file_task_running=True
                try:run_file_task(self.root,'Saving Project',lambda cancel,progress:export_project(self.case,self.case_dir,path,cancel=cancel,progress=progress))
                finally:self._file_task_running=False
                self._project_file=Path(path);self._saved_project_fingerprint=fingerprint(self.case,self.case_dir)
                self.status.set('Project saved: '+str(path));return True
            except InterruptedError:
                self.status.set('Saving cancelled. Your previous saved project is unchanged.');return False
            except Exception as exc:messagebox.showerror('Cannot Save Project',str(exc));return False
        finally:self.start_photo_work()

    def prepare_leave(self):
        if getattr(self,'_file_task_running',False):return False
        service=self._background_photos
        if service and service.case is self.case:service.cancel.set()
        if service and service.running:
            self.status.set('Finishing the current photo. Try closing or opening a project again in a moment.');return False
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
        card=getattr(self,'_load_card_review',None)
        if card and not card.closed:card.close()
        if self._background_photos:self._background_photos.close();self._background_photos=None
        for window in getattr(self,'_photo_sorting_windows',[]):
            if not window.closed:window.close()
        if self._case_temp is not None:self._case_temp.cleanup();self._case_temp=None

    def open_case(self):
        if getattr(self,'_file_task_running',False):return
        if self.finish_photo_work(self.open_case):return
        import tempfile
        from portable_project import import_project,fingerprint
        path=filedialog.askopenfilename(title='Open Project',filetypes=[('ED Project','*.edcase'),('Older Case','case.json')])
        if not path:self.start_photo_work();return
        if not self.prepare_leave():self.start_photo_work();return
        owner=None
        try:
            self.status.set('Opening project...');self.root.update_idletasks()
            if Path(path).suffix.lower()=='.edcase':
                owner=tempfile.TemporaryDirectory(prefix='ed-project-');directory=Path(owner.name)
                from background_task import run_file_task
                self._file_task_running=True
                try:case=run_file_task(self.root,'Opening Project',lambda cancel,progress:import_project(path,directory,cancel=cancel,progress=progress))
                finally:self._file_task_running=False
            else:directory=Path(path).parent;case=json.loads(Path(path).read_text(encoding='utf-8'))
            self.release_temporary_case();self.case=case;self.case_dir=directory;self._case_temp=owner
            self._project_file=Path(path) if owner else None;self.vars={};self.refresh();self.go(0)
            self._saved_project_fingerprint=fingerprint(self.case,self.case_dir) if owner else None
            if owner:self.status.set('Project opened · Temporary session. Use Save Project to keep changes.')
        except InterruptedError:
            if owner:owner.cleanup()
            self.status.set('Opening cancelled. Your current case is still open.')
        except Exception as exc:
            if owner:owner.cleanup()
            messagebox.showerror('Cannot Open Project',str(exc))
        finally:self.start_photo_work()

    def close_app(self):
        if getattr(self,'_file_task_running',False):return
        if self.finish_photo_work(self.close_app):return
        if not self.prepare_leave():self.start_photo_work();return
        if self.case:self.save()
        self.release_temporary_case();self.root.destroy()
        from small_vision_runtime import RUNTIME
        RUNTIME.stop()

    def new_case(self):
        if getattr(self,'_file_task_running',False):return
        if self.finish_photo_work(self.new_case):return
        if self.case: self.save()
        win=tk.Toplevel(self.root);win.title('New Case');win.transient(self.root);fit_window(win,self.root,(520,420),(480,320));win.grab_set()
        actions=ttk.Frame(win,padding=(24,16));actions.pack(side='bottom',fill='x')
        content=ttk.Frame(win);content.pack(fill='both',expand=True)
        body=self.scroll_page(content);body.configure(padding=24)
        ttk.Label(body,text='Create a Case',font=(self.ui_font,20,'bold')).pack(anchor='w')
        ttk.Label(body,text='Just the essentials. Add files next.',style='Muted.TLabel').pack(anchor='w',pady=(6,20))
        values={};first_entry=None
        for label,key in [('Case Number','case_number'),('Vendor','vendor')]:
            row=ttk.Frame(body);row.pack(fill='x',pady=8);ttk.Label(row,text=label,width=15).pack(side='left')
            var=tk.StringVar();values[key]=var;entry=ttk.Entry(row,textvariable=var);entry.pack(side='left',fill='x',expand=True)
            if first_entry is None:first_entry=entry
        previous_case=self.case
        def cancel():
            win.destroy()
            if self.case is previous_case:self.start_photo_work()
        win.protocol('WM_DELETE_WINDOW',cancel);win.bind('<Escape>',lambda event:cancel())
        def create():
            case=values['case_number'].get().strip();vendor=values['vendor'].get().strip()
            if not case or not vendor: messagebox.showwarning('Required Details','Enter the case number and vendor.',parent=win);return
            if not self.prepare_leave():return
            import tempfile
            self.release_temporary_case();self._case_temp=tempfile.TemporaryDirectory(prefix='ed-project-');directory=Path(self._case_temp.name)
            self._project_file=None;self._saved_project_fingerprint=None
            self.case=make_case(case,'',vendor,1,'');self.case['verified_first_10_amount']=''
            self.case_dir=directory;self.vars={};self.save();self.refresh();self.go(0);win.destroy()
        first_entry.focus_set();win.bind('<Return>',lambda event:create())
        ttk.Button(actions,text='Cancel',command=cancel).pack(side='left')
        ttk.Button(actions,text='Create Case',style='Primary.TButton',command=create).pack(side='right')

    def draw_case(self):
        if not self.case:self.empty(self.case_tab);return
        self.clear(self.case_tab)
        header=self.card(self.case_tab,'Import the Vendor Files','Import the folder or ZIP you received. The app keeps the originals and prepares document suggestions for review.')
        row=ttk.Frame(header,style='Card.TFrame');row.pack(fill='x',pady=6)
        ttk.Button(row,text='Import Folder',style='Primary.TButton',command=self.import_files).pack(side='left')
        ttk.Button(row,text='Import ZIPs',command=self.import_zips).pack(side='left',padx=8)
        ttk.Button(row,text='Organize Photos',command=self.organize_photos).pack(side='left')
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
        if getattr(self,'_file_task_running',False) or not self.require():return False
        import tempfile
        from evidence_intake import stage_import,commit_import
        from background_task import run_file_task
        self.save();case=self.case
        try:
            with tempfile.TemporaryDirectory(prefix='.ed-import-',dir=self.case_dir) as staging:
                existing={r['sha256'] for r in case.get('imported_files',[]) if r.get('sha256')}
                self._file_task_running=True
                try:result=run_file_task(self.root,'Importing Vendor Files',lambda cancel,progress:dict(stage_import(files,existing,staging,cancel,progress),cancel=cancel))
                finally:self._file_task_running=False
                if self.case is not case:raise ValueError('The case changed before import finished.')
                if result['cancel'].is_set():raise InterruptedError('Import cancelled.')
                records,documents=commit_import(result,self.case_dir/'originals')
                case.setdefault('imported_files',[]).extend(records)
                case.setdefault('package_documents',[]).extend(documents)
            case['photo_suggestions']=[photo_suggestion(r) for r in case.get('imported_files',[]) if Path(r['path']).suffix.lower() in IMAGE_EXT]
            self.save();self.refresh();self.go(0)
            if result['issues']:
                try:(self.case_dir/'import_warnings.txt').write_text('\n'.join(result['issues']),encoding='utf-8')
                except OSError:pass
            self.status.set(f"Files Imported · {len(records)} Added · {result['duplicates']} Exact Duplicates · {len(result['issues'])} Warnings")
            messagebox.showinfo('Import Complete',f"Files added: {len(records)}\nExact duplicates skipped: {result['duplicates']}\nWarnings: {len(result['issues'])}"+('\n\n'+ '\n'.join(result['issues'][:5]) if result['issues'] else '')+'\n\nReview document purposes, then continue to Review Loads.')
            return True
        except InterruptedError:self.status.set('Import cancelled. No new files were added.');return False
        except Exception as exc:messagebox.showerror('Cannot Import Files',str(exc));return False
        finally:self.start_photo_work()

    def add_bid(self):
        self.add_document(purpose='bid')

    def add_document(self,purpose=None):
        if not self.require():return
        paths=filedialog.askopenfilenames(title='Add Bid Files' if purpose=='bid' else 'Add Invoices, Bids or Supporting Documents',filetypes=[('Images and Documents','*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.docx')])
        if not paths:return
        digests={hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
        if not self._import_paths([Path(p) for p in paths]):return
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
        from calculator_evidence import file_digest
        try:opened_digest=file_digest(item['path'])
        except OSError as exc:messagebox.showerror('Cannot Review Document',str(exc));return
        reviewed_case=self.case
        win=tk.Toplevel(self.root);win.title('Review Package Document');win.transient(self.root);fit_window(win,self.root,(680,650),(560,400));win.grab_set()
        footer=ttk.Frame(win,padding=(20,12));footer.pack(side='bottom',fill='x')
        content=ttk.Frame(win);content.pack(fill='both',expand=True)
        body=self.scroll_page(content);body.configure(padding=24)
        title=ttk.Label(body,text=item.get('name','Document'),font=(self.ui_font,13,'bold'),wraplength=570);title.pack(fill='x',pady=(0,10))
        title.bind('<Configure>',lambda e:title.configure(wraplength=max(200,e.width)))
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
        quantity_line=ttk.Frame(quantity_row);quantity_line.pack(fill='x')
        ttk.Label(quantity_line,text='Debris Quantity on Bid (CYD)',width=31).pack(side='left')
        values['debris_quantity_cyd']=tk.StringVar(value=item.get('debris_quantity_cyd',''))
        ttk.Entry(quantity_line,textvariable=values['debris_quantity_cyd']).pack(side='left',fill='x',expand=True)
        rate_row=ttk.Frame(quantity_row);rate_row.pack(fill='x',pady=(6,0))
        ttk.Label(rate_row,text='Price per CYD ($), Only if Shown').pack(side='left')
        values['unit_rate_per_cyd']=tk.StringVar(value=item.get('unit_rate_per_cyd',''))
        ttk.Entry(rate_row,textvariable=values['unit_rate_per_cyd'],width=12).pack(side='right')
        def show_bid_quantity(*args):
            if role.get()==ROLES['bid']:quantity_row.pack(fill='x',pady=7,after=bid_fields_end)
            else:quantity_row.pack_forget()
        role.trace_add('write',show_bid_quantity);show_bid_quantity()
        def confirm(split=False):
            if self.case is not reviewed_case:
                messagebox.showwarning('Case Changed','Open this document again in the current case.',parent=win);return
            record=dict(item,role=next(key for key,value in ROLES.items() if value==role.get()),confirmed=True,**{key:value.get().strip() for key,value in values.items()})
            try:
                import fitz
                from cor_package import parse_pages
                if file_digest(record['path'])!=opened_digest:raise ValueError('This document changed. Close and reopen it before confirming.')
                record['reviewed_sha256']=opened_digest
                if Path(record['path']).suffix.lower()=='.pdf':
                    with fitz.open(record['path']) as source:parse_pages(record.get('pages'),len(source))
                if record['role']=='bid':
                    number(record['amount'])
                    record['pricing_basis']='per_cyd' if record.get('unit_rate_per_cyd') else 'fixed_total'
                    if record['pricing_basis']=='per_cyd':
                        from cor_package import comparable_bid_amount
                        comparable_bid_amount(record,record['debris_quantity_cyd'])
                    if number(record['debris_quantity_cyd'])<=0:raise ValueError('Enter the debris quantity shown on this bid.')
            except Exception as exc:messagebox.showwarning('Check Document Details',str(exc),parent=win);return
            if split:self.case['package_documents'].append(record)
            else:self.case['package_documents'][index]=record
            self.case['bid_review_confirmed']=False;self.save();self.draw_case();win.destroy()
        row=footer
        ttk.Button(row,text='Cancel',command=win.destroy).pack(side='left',padx=(0,8))
        win.bind('<Escape>',lambda event:win.destroy())
        ttk.Button(row,text='Add as Another Section',command=lambda:confirm(True)).pack(side='left')
        ttk.Button(row,text='Confirm Document',style='Primary.TButton',command=confirm).pack(side='right')

    def scan_photos(self,records=None,review_when_done=False,on_complete=None,background=False):
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
                current=cache.get(item['path'],{})
                source=self.case.get('local_photo_results',{}).get(item['path'],{})
                if 'timing_text' not in current and source.get('sha256')==digest and (source.get('card_detected') or source.get('card_regions') or source.get('prediction',{}).get('category') in ('container_photos','measurement')):
                    from local_reader import read_timestamp
                    from visual_photo_review import timing_clues
                    clues=timing_clues(item['path'],text)
                    timing='' if not clues['flags'] and any(c.get('date') and c.get('time') for c in clues['clues']) else read_timestamp(item['path'])[0]
                    if file_digest(item['path'])!=digest:
                        notes.append('A source changed during date/time reading.');cache.pop(item['path'],None);continue
                    current['timing_text']=timing;cache[item['path']]=current
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
            if not background and self.current_step()==0:self.draw_case()
            if not background and self.current_step()==2:self.draw_finance()
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
        self.save();self._template_review=TemplateReviewWindow(self);self.start_photo_work()

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

    def start_photo_work(self):
        if not self.case:return
        from photo_flow import BackgroundPhotoWork
        previous=self._background_photos
        paths={r['path'] for r in self.case.get('imported_files',[]) if Path(r['path']).suffix.lower() in IMAGE_EXT}
        if not paths:return
        more=previous and not paths.issubset(previous.record_paths)
        if previous and previous.case is self.case and not previous.closed and not previous.cancel.is_set() and not more:return previous
        if previous and previous.running:
            previous.cancel.set()
            if not getattr(previous,'restart_pending',False):
                previous.restart_pending=True;case=self.case
                def restart():
                    if self.case is not case:return
                    if previous.running:self.root.after(300,restart);return
                    self.start_photo_work()
                self.root.after(300,restart)
            return previous
        if previous:previous.close()
        self._background_photos=BackgroundPhotoWork(self)
        return self._background_photos

    def review_load_cards(self):
        if not self.require():return
        previous=getattr(self,'_load_card_review',None)
        if previous and not previous.closed and previous.case is self.case:previous.win.lift();return
        from load_card_review import CardReviewWindow
        CardReviewWindow(self)
    def organize_photos(self):
        if not self.require():return
        from photo_flow import PhotoFlowWindow
        previous=getattr(self,'_photo_flow',None)
        if previous and not previous.closed and previous.case is self.case:self.start_photo_work();previous.win.lift();return
        self._photo_flow=PhotoFlowWindow(self)

    def draw_evidence(self):
        super().draw_evidence()
        if not self.case:return
        legacy=list(self.evidence_tab.winfo_children())
        for child in legacy:child.pack_forget()
        surface=ttk.Frame(self.evidence_tab);surface.pack(fill='both',expand=True)
        content=self.scroll_page(surface)
        row=ttk.Frame(content,padding=(0,0,0,10))
        row.pack(fill='x')
        ttk.Button(row,text='Review Load Cards',command=self.review_load_cards).pack(side='left',padx=(0,8))
        ttk.Button(row,text='1 · Organize Photos',style='Primary.TButton',command=self.organize_photos).pack(side='left')
        ttk.Button(row,text='2 · Fill Template',command=self.template_photo_review).pack(side='left',padx=8)
        details=ttk.Frame(content,padding=(0,0,0,10));details.pack(fill='x')
        ttk.Button(details,text='Container Details',command=self.measurements).pack(side='left')
        options=ttk.Menubutton(details,text='More');menu=tk.Menu(options,tearoff=False);options.configure(menu=menu);options.pack(side='right')
        menu.add_command(label='Advanced Photo Review',command=self.visual_photo_review)
        def manual():
            for child in list(self.evidence_tab.winfo_children()):
                if child not in legacy:child.pack_forget()
            for child in legacy:child.pack(fill='both',expand=True)
        menu.add_command(label='Manual Photo Assignment',command=manual)
        card=self.card(content,'Review the Cards, Then the Photos','If the vendor supplied load cards, confirm them first. Review each suggested group, then choose the clearest evidence for the template.')
        instructions=card
        for text,muted in [('Photo sorting and text reading run locally in the background. Use the visible load cards and loading progress to confirm each trip.',False),('Same container, different loads? Keep the trips separate. Dates can help with order, but a date alone does not establish the trip or fill level.',True)]:
            label=ttk.Label(card,text=text,wraplength=580,style='Card.TLabel',foreground=MUTED if muted else guided_ui.INK)
            label.pack(anchor='w',fill='x',pady=(12,0))
            label.bind('<Configure>',lambda event,w=label:w.configure(wraplength=max(180,event.width)),add='+')
        from workflow_status import package_inventory
        loads=[r for r in package_inventory(self.case) if r['kind']=='template']
        card=self.card(content,'Loads in This Package','Select a load to continue where its evidence needs attention.')
        card.pack_configure(before=instructions)
        listing=ttk.Frame(card,style='Card.TFrame');listing.pack(fill='x',pady=(10,8))
        self.load_progress=ttk.Treeview(listing,columns=('next',),show='tree headings',height=min(6,max(1,len(loads))),selectmode='browse')
        tree=self.load_progress;tree.heading('#0',text='Load');tree.heading('next',text='Next Action')
        tree.column('#0',width=90,minwidth=70,stretch=False);tree.column('next',width=420,minwidth=180)
        scroll=ttk.Scrollbar(listing,command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set);tree.pack(fill='x')
        for item in loads:tree.insert('','end',iid=str(item['load']),text=item['label'],values=(item['detail'],))
        def choose(event=None):
            if tree.selection():self.e_load.set(tree.selection()[0])
        def resume(event=None):
            choose();self.template_photo_review()
        tree.bind('<ButtonRelease-1>',choose);tree.bind('<KeyRelease>',choose);tree.bind('<Double-1>',resume)
        current=self.e_load.get()
        if current in tree.get_children():tree.selection_set(current)
        elif tree.get_children():tree.selection_set(tree.get_children()[0])
        ttk.Button(card,text='Review Selected Load',style='Primary.TButton',command=resume).pack(anchor='e',pady=(6,0))

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
        rounding=tk.StringVar(value='Round Capacity Before Applying Fill' if load.get('quantity_rounding')=='capacity_then_fill' else 'Keep Full Precision Until Load Total')
        ttk.Label(advanced,text='Calculation Rounding — Match the Attached Calculation').pack(anchor='w')
        ttk.Combobox(advanced,textvariable=rounding,state='readonly',values=['Keep Full Precision Until Load Total','Round Capacity Before Applying Fill'],width=48).pack(anchor='w',pady=5)
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
                proposed['quantity_rounding']='capacity_then_fill' if rounding.get()=='Round Capacity Before Applying Fill' else 'full_precision'
                calculated=volume(proposed)
            except Exception as exc:messagebox.showwarning('Measurements Need Review',str(exc),parent=win);return False
            load.update(proposed);load['include_supporting_measurements']=supporting.get();load['measurements_confirmed']=True;self.case['bid_review_confirmed']=False
            self.save();result.configure(text=f'Confirmed: {calculated["total"]:.2f} CYD')
            self.refresh_load_progress()
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

    def performance_check(self):
        if not self.require():return
        if self.finish_photo_work(self.performance_check):return
        import copy,queue
        from workflow_metrics import measure
        results=queue.Queue();snapshot=copy.deepcopy(self.case);directory=self.case_dir;owner=self.case
        self.status.set('Checking local storage and photo-review performance...')
        def work():
            try:results.put((measure(snapshot,directory),None))
            except Exception as exc:results.put((None,str(exc)))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            try:data,error=results.get_nowait()
            except queue.Empty:self.root.after(100,poll);return
            if self.case is not owner:return
            self.start_photo_work()
            self.status.set('Local performance check complete.' if not error else 'Performance check could not finish.')
            if error:messagebox.showwarning('Performance Check',error,parent=self.root);return
            text=f"Photos: {data['photos']} ({data['analyzed_photos']} analyzed)\nReview preparation: {data['cold_seconds']} seconds\nCached preparation: {data['cached_seconds']} seconds\nWorking project: {data['project_mb']} MB\nLocal models: {data['model_mb']} MB\nFree disk: {data['free_disk_mb']} MB\n\n"+data['note']
            messagebox.showinfo('Storage and Performance',text,parent=self.root)
        self.root.after(100,poll)
    def recover_export(self):
        from export_bundle import recover_bundles
        folder=filedialog.askdirectory(parent=self.root,title='Choose the Export Folder')
        if not folder:return
        try:messagebox.showinfo('Export Recovery',f'{recover_bundles(folder)} interrupted export(s) restored.',parent=self.root)
        except Exception as exc:messagebox.showerror('Recovery Needs Attention',str(exc),parent=self.root)
    def choose_invoice_version(self):
        from invoice_review import use_invoice_version
        win=tk.Toplevel(self.root);win.title('Choose Final Invoice');win.transient(self.root)
        ttk.Label(win,text='Open and check the final version. Other invoice versions remain in your project but are excluded from the package.',wraplength=550).pack(padx=18,pady=12)
        def choose(index):
            try:
                use_invoice_version(self.case,index);self.save();win.destroy();self.draw_finance()
            except Exception as exc:messagebox.showwarning('Invoice Needs Review',str(exc),parent=win)
        for index,doc in enumerate(self.case.get('package_documents',[])):
            if doc.get('role')!='invoice':continue
            line=ttk.Frame(win,padding=8);line.pack(fill='x')
            ttk.Button(line,text='Open '+doc.get('name',Path(doc['path']).name),command=lambda p=doc['path']:self.open_original(p)).pack(side='left')
            ttk.Button(line,text='Use This Version',command=lambda i=index:choose(i)).pack(side='right')
    def keep_invoice_set(self):
        from invoice_review import confirm_invoice_set
        if not messagebox.askyesno('Confirm Final Bill','Do these attachments form one final bill, with no replaced versions or duplicate charges? Enter the combined invoice total once.',parent=self.root):return
        try:confirm_invoice_set(self.case);self.save();self.draw_finance()
        except Exception as exc:messagebox.showwarning('Invoice Needs Review',str(exc),parent=self.root)
    def draw_finance(self):
        if not self.case:self.empty(self.finance_tab);return
        from cor_package import extract_costs
        # Readable suggestions are populated once; entered values are never overwritten.
        invoices=[d for d in self.case.get('package_documents',[]) if d.get('role')=='invoice']
        suggestions={}
        if len(invoices)==1:
            invoice=invoices[0]
            from calculator_evidence import file_digest
            try:current_sha=file_digest(invoice['path'])
            except OSError:current_sha=None
            expected=invoice.get('cost_suggestions_sha256') or invoice.get('reviewed_sha256') or next((r.get('sha256') for r in self.case.get('imported_files',[]) if r['path']==invoice['path']),None)
            if current_sha and (not expected or current_sha==expected):suggestions=dict(invoice.get('cost_suggestions',{}))
            cached=self.case.get('photo_text_cache',{}).get(invoice['path'],{})
            if cached.get('text'):
                from calculator_evidence import file_digest
                try:current=cached.get('sha256')==file_digest(invoice['path'])
                except OSError:current=False
                if current:suggestions.update(extract_costs(cached['text']))
            for key,value in suggestions.items():
                if self.case.get(key) in ('',None):self.case[key]=value
        content=self.scroll_page(self.finance_tab);self.finance_displays={}
        card=self.card(content,'1. Check the Invoice','Figures read from the invoice are suggestions. Compare them with the original and correct anything that is wrong.')
        for invoice in invoices:
            ttk.Button(card,text='Open Invoice' if len(invoices)==1 else 'Open Invoice · '+invoice.get('name',Path(invoice['path']).name),command=lambda p=invoice['path']:self.open_original(p)).pack(anchor='w',pady=(0,8))
        if len(invoices)>1:
            ttk.Label(card,text='Choose the final invoice version, or keep all attachments if they make up one final bill.',style='Card.TLabel',wraplength=580).pack(anchor='w',pady=6)
            ttk.Button(card,text='Choose Final Invoice Version',command=self.choose_invoice_version).pack(anchor='w',pady=4)
            ttk.Button(card,text='Keep These Attachments as the Final Bill',command=self.keep_invoice_set).pack(anchor='w',pady=4)
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
            try:
                from cor_package import comparable_bid_amount
                return comparable_bid_amount(d,totals(self.case)['quantity'])
            except (ValueError,KeyError):return number('999999999')
        ordered=sorted(bids,key=bid_sort);lines=[]
        for i,d in enumerate(ordered):
            name=d.get('vendor') or d.get('name','Bid')
            try:
                from cor_package import comparable_bid_amount
                comparison=comparable_bid_amount(d,totals(self.case)['quantity'])
                label=('Lowest Comparable Bid: ' if i==0 else '')+f"{name}: ${d.get('amount')}"
                if d.get('pricing_basis')=='per_cyd':label+=f' · ${comparison:.2f} at Measured Quantity'
            except (ValueError,KeyError):label=f'{name}: Check Bid Quantity and Price'
            lines.append(label)
        listing='\n'.join(lines) or 'No bids attached yet.'
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
        invoices=[d for d in self.case.get('package_documents',[]) if d.get('role')=='invoice']
        prompt='Have you checked the invoice, the photo-supported quantity, and the calculated first-10-CYD deduction at the request rate?'
        if len(invoices)>1:prompt=f'Have you checked all {len(invoices)} invoice attachments, excluded replaced versions, and entered the combined final figures with Initial Services deducted only once?'
        if not messagebox.askyesno('Confirm Invoice Details',prompt):return
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
            from cor_package import comparable_bid_amount
            value=totals(self.case);amounts=[comparable_bid_amount(d,value['quantity']) for d in bids]
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

    def package_overview(self):
        if not self.require():return
        from workflow_status import package_inventory
        rows=package_inventory(self.case)
        win=tk.Toplevel(self.root);win.configure(background=BG);win.title('Package Overview');win.geometry('850x620');win.minsize(650,450)
        ttk.Label(win,text='Package Overview',font=(self.ui_font,20,'bold')).pack(anchor='w',padx=18,pady=16)
        ttk.Label(win,text='Open an item to continue. Attached files still undergo source and cost checks before export.',wraplength=780).pack(anchor='w',padx=18)
        body=ttk.Frame(win,padding=18);body.pack(fill='both',expand=True)
        tree=ttk.Treeview(body,columns=('next',),show='tree headings',selectmode='browse')
        tree.heading('#0',text='Package Section');tree.heading('next',text='Next Action / Status')
        tree.column('#0',width=220);tree.column('next',width=450)
        scrollbar=ttk.Scrollbar(body,command=tree.yview);scrollbar.pack(side='right',fill='y')
        tree.configure(yscrollcommand=scrollbar.set);tree.pack(fill='both',expand=True)
        for i,row in enumerate(rows):tree.insert('','end',iid=str(i),text=row['label'],values=(row['detail'],))
        def resume():
            if not tree.selection():return
            row=rows[int(tree.selection()[0])];win.destroy()
            if row['kind']=='template':
                self.e_load.set(str(row['load']));self.template_photo_review()
                window=getattr(self,'_template_review',None)
                if window and row.get('slot'):window.refresh_tree(row['slot']);window.reset_page()
            elif row['kind']=='stage':
                self.organize_photos();window=self._photo_flow
                window.category.set('property_photos');window.target.set(row['label']);window.target_help();window.reset_page()
            else:self.go(row['step'])
        ttk.Button(win,text='Continue Selected Item',style='Primary.TButton',command=resume).pack(anchor='e',padx=18,pady=(0,16))
        tree.bind('<Double-1>',lambda e:resume())
        if rows:tree.selection_set('0')

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
        ttk.Button(actions,text='Package Overview',command=self.package_overview).pack(side='left')
        ttk.Button(actions,text='Go to Selected Step',command=self.resolve_issue).pack(side='left',padx=7)
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
        detail=ttk.Label(self.check_tab,text='Select an item to read the full details, then open its step.',wraplength=580,justify='left')
        detail.pack(fill='x',pady=(10,0))
        detail.bind('<Configure>',lambda event:detail.configure(wraplength=max(180,event.width)),add='+')
        def selected(event=None):
            rows=tree.selection()
            detail.configure(text=tree.item(rows[0],'text') if rows else 'Select an item to read the full details, then open its step.')
        tree.bind('<<TreeviewSelect>>',selected)
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

    def export_result(self,report,pdf):
        win=tk.Toplevel(self.root);win.title('Package Saved');win.transient(self.root)
        fit_window(win,self.root,(660,420),(500,320))
        body=ttk.Frame(win,padding=26);body.pack(fill='both',expand=True)
        complete=report['status']=='Complete'
        ttk.Label(body,text='Your Package Is Saved' if complete else 'Your Draft Is Saved',font=(self.ui_font,21,'bold')).pack(anchor='w')
        detail=f'{report["pages"]} pages · All package checks passed.' if complete else f'{report["pages"]} pages · {len(report["issues"])} items still need attention.'
        ttk.Label(body,text=detail,style='Muted.TLabel',wraplength=580).pack(anchor='w',pady=(8,20))
        ttk.Label(body,text=pdf.name,font=(self.ui_font,11,'bold'),wraplength=580).pack(anchor='w')
        ttk.Label(body,text=str(pdf.parent),style='Muted.TLabel',wraplength=580).pack(anchor='w',pady=(6,16))
        note='The request description is saved beside the PDF.' if complete else 'Return to Create Package to resolve the remaining items. A request description is saved only when the checks pass.'
        ttk.Label(body,text=note,wraplength=580,justify='left').pack(anchor='w')
        actions=ttk.Frame(body);actions.pack(side='bottom',fill='x',pady=(20,0))
        ttk.Button(actions,text='Open PDF',style='Primary.TButton',command=lambda:self.open_original(pdf)).pack(side='left')
        ttk.Button(actions,text='Open Folder',command=self.open_output).pack(side='left',padx=10)
        def finish():
            win.destroy()
            if not complete:self.go(3)
        ttk.Button(actions,text='Done' if complete else 'Review Remaining Items',command=finish).pack(side='right')

    def generate(self):
        if getattr(self,'_file_task_running',False):return
        if not self.require():return
        if self.finish_photo_work(self.generate):return
        try:
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
                import copy
                from background_task import run_file_task
                snapshot=copy.deepcopy(self.case)
                def create_package(cancel,progress):
                    staged=folder/(safe(snapshot['case_number'])+'_COR_PACKAGE_DRAFT.pdf')
                    report=assemble(snapshot,staged,issues,cancel=cancel,progress=progress)
                    if destination:
                        if cancel.is_set():raise InterruptedError('Package creation cancelled.')
                        from export_bundle import publish_bundle
                        progress('Saving to your chosen folder...')
                        text=folder/'COR_Request_Description.txt'
                        publish_bundle([(Path(destination),staged),
                                        (Path(destination).with_suffix('.description.txt'),text if text.is_file() else None),
                                        (Path(destination).with_suffix('.review.json'),folder/'Package_Review.json')])
                    return report
                self._file_task_running=True
                try:report=run_file_task(self.root,'Creating COR Package',create_package)
                finally:self._file_task_running=False
                if destination:self.status.set('Package saved: '+str(destination))
                self._last_export_case_dir=self.case_dir
                self._last_export_folder=Path(destination).parent if destination else folder
                saved_pdf=Path(destination) if destination else folder/(safe(self.case['case_number'])+'_COR_PACKAGE_DRAFT.pdf')
                self.status.set('Package saved: '+str(saved_pdf))
                self.export_result(report,saved_pdf)
            except InterruptedError:self.status.set('Package creation cancelled. Your previous saved package is unchanged.')
            except Exception as exc:messagebox.showerror('Package Export Failed',str(exc))
        finally:self.start_photo_work()

