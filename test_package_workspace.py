import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from PIL import Image, ImageDraw
from package_ui import PackageApp
from calculator_evidence import measurement_signature, file_digest
from cor_package import bid_fingerprint, financial_fingerprint
from test_cor_package import fixture

class PackageWorkspaceTests(unittest.TestCase):
    def setUp(self):
        # An unexpected error must fail CI instead of waiting in an unseen dialog.
        dialog=patch('tkinter.messagebox.showerror',side_effect=AssertionError('Unexpected application error dialog'))
        dialog.start();self.addCleanup(dialog.stop)
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=PackageApp(self.root)
        background=patch.object(self.app,'start_photo_work');background.start();self.addCleanup(background.stop)
        self.app.case=fixture(self.folder);self.app.case_dir=self.folder
        # Unique synthetic sources make the reuse audit meaningful during end-to-end validation.
        counter=0
        def source():
            nonlocal counter
            counter+=1;path=self.folder/f'evidence_{counter}.png'
            image=Image.new('RGB',(400,300),(counter*3%255,counter*7%255,counter*11%255))
            ImageDraw.Draw(image).text((12,12),f'SYNTHETIC TEST EVIDENCE {counter}',fill='white');image.save(path);return str(path)
        for load in self.app.case['loads']:
            for key in load['photos']:load['photos'][key]=source()
            load['disposal_photo']=source();load['evidence_first_10_cyd']=source()
            load['extra_measurement_photos']=[source(),source(),source()]
            load['calculator_evidence']['path']=source()
            load['calculator_evidence']['sha256']=file_digest(load['calculator_evidence']['path'])
        for key in ('before_photos','during_photos','after_photos'):self.app.case[key]=[source()]
        from visual_photo_review import apply_visual_stage
        for stage,phase in [('before','before_photos'),('during','during_photos'),('after','after_photos')]:
            apply_visual_stage(self.app.case,list(self.app.case[phase]),stage,visually_checked=True)
        self.app.case['financial_confirmation_note']='Synthetic Test Reference'
        self.app.case['bid_confirmation_hash']=bid_fingerprint(self.app.case)
        self.app.case['financial_confirmation_hash']=financial_fingerprint(self.app.case)
        self.app.refresh();self.root.update()

    def tearDown(self):self.root.destroy();self.temp.cleanup()

    def widgets(self,parent):
        for child in parent.winfo_children():
            yield child
            yield from self.widgets(child)

    def text_suggestion_fixture(self):
        path=self.folder/'load-card.png';Image.new('RGB',(500,500),'white').save(path)
        self.app.case['imported_files']=[dict(path=str(path),name='Misleading Load 99 Empty.jpg')]
        self.app.case['photo_text_cache']={str(path):dict(sha256=file_digest(path),text='Load 1\n19 ft x 7.8 ft x 6.5 ft\nL W H')}
        for key in ('length_ft','width_ft','side_height_ft'):self.app.case['loads'][0][key]=''
        self.app.review_suggestions();self.root.update()
        window=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
        widgets=list(self.widgets(window));tree=next(w for w in widgets if isinstance(w,tk.ttk.Treeview))
        tree.selection_set('0')
        button=next(w for w in widgets if isinstance(w,tk.ttk.Button) and w.cget('text')=='Apply Selected Suggestions')
        return path,button

    def test_reviewed_load_card_suggestions_persist_without_auto_confirmation(self):
        path,button=self.text_suggestion_fixture()
        with patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showwarning') as warning:button.invoke()
        warning.assert_not_called()
        self.assertEqual(self.app.case['loads'][0]['length_ft'],'19')
        self.assertFalse(self.app.case['loads'][0]['measurements_confirmed'])
        import json
        saved=json.loads((self.folder/'case.json').read_text())
        self.assertEqual(saved['loads'][0]['width_ft'],'7.8')
        self.assertEqual(len(saved['loads']),3)
        self.assertEqual(self.errors,[])

    def test_changed_source_is_rejected_from_open_suggestion_dialog(self):
        path,button=self.text_suggestion_fixture();path.write_bytes(b'changed')
        with patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showwarning') as warning:button.invoke()
        warning.assert_called_once()
        self.assertIn('source photo',warning.call_args.args[1])
        self.assertEqual(self.app.case['loads'][0]['length_ft'],'')
        self.assertEqual(self.errors,[])

    def test_read_selected_photo_button_reads_only_that_photo(self):
        path=self.folder/'card.png';Image.new('RGB',(400,400),'white').save(path)
        record=dict(path=str(path),name=path.name);self.app.case['imported_files']=[record];self.app.selected_photo=str(path)
        self.app.measurements();self.root.update()
        button=next(w for w in self.widgets(self.root) if isinstance(w,tk.ttk.Button) and w.cget('text')=='Read Selected Photo Text')
        with patch.object(self.app,'scan_photos') as scan:button.invoke()
        scan.assert_called_once_with([record],review_when_done=True)

    def test_no_supplemental_count_warning_for_template_complete_case(self):
        for load in self.app.case['loads']:load['extra_measurement_photos']=[]
        self.assertEqual(self.app.evaluate()[3],[])
        self.app.refresh_assignments()
        for key in ('measurement_extra_1','measurement_extra_2','measurement_extra_3'):
            self.assertEqual(self.app.assignment_tree.item(key,'values'),('Optional',))

    def test_supporting_measurement_export_preference_is_saved(self):
        self.app.measurements();self.root.update()
        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)
        children=list(widgets(self.root))
        toggle=next(w for w in children if isinstance(w,tk.ttk.Checkbutton) and w.cget('text')=='Include Supporting Measurement Photos in Package')
        self.assertFalse(bool(int(toggle.getvar(toggle.cget('variable')))))
        toggle.invoke()
        next(w for w in children if isinstance(w,tk.ttk.Button) and w.cget('text')=='Confirm Measurements').invoke()
        self.assertTrue(self.app.case['loads'][0]['include_supporting_measurements'])
        import json
        saved=json.loads((self.folder/'case.json').read_text())
        self.assertTrue(saved['loads'][0]['include_supporting_measurements'])

    def test_complete_export_through_actual_app(self):
        self.assertEqual(self.app.evaluate()[3],[])
        with patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error,patch.object(self.app,'open_output'):
            self.app.generate()
        error.assert_not_called()
        self.assertTrue((self.folder/'output'/'TEST-001_COR_PACKAGE_DRAFT.pdf').is_file())
        self.assertIn('$1,049.65',(self.folder/'output'/'COR_Request_Description.txt').read_text())

    def test_partial_load_is_consistent_through_actual_app_validation(self):
        load=self.app.case['loads'][0];load['fill_fraction']='.5';load['measurements_confirmed']=True
        for slot in ('three_quarters','full_1','full_2'):load['photos'].pop(slot,None)
        issues=self.app.evaluate()[3]
        self.assertFalse(any('missing template image '+slot in issue or 'Add '+slot.replace('_',' ')+' evidence' in issue for slot in ('three_quarters','full_1','full_2') for issue in issues))

    def test_incomplete_external_export_removes_previous_description(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'package.pdf';description=pdf.with_suffix('.description.txt')
            pdf.write_bytes(b'previous pdf');description.write_text('previous payable description')
            self.app.case['financial_confirmation_hash']='expired'
            with patch.object(self.app,'_case_temp',object()),patch('tkinter.filedialog.asksaveasfilename',return_value=str(pdf)),patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error:
                self.app.generate()
            error.assert_not_called();self.assertFalse(description.exists())
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))

    def test_external_export_keeps_report_and_opens_chosen_folder(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'chosen.pdf'
            with patch.object(self.app,'_case_temp',object()),patch('tkinter.filedialog.asksaveasfilename',return_value=str(pdf)),patch.object(self.app,'export_result') as result,patch('tkinter.messagebox.showerror') as error:
                self.app.generate()
            error.assert_not_called()
            self.assertTrue(pdf.is_file())
            self.assertEqual(json.loads(pdf.with_suffix('.review.json').read_text())['status'],'Complete')
            self.assertIn('$1,049.65',pdf.with_suffix('.description.txt').read_text())
            self.assertEqual(result.call_args.args[1],pdf)
            with patch('guided_ui.sys.platform','win32'),patch('guided_ui.os.startfile',create=True) as opened:
                self.app.open_output()
            opened.assert_called_once_with(str(pdf.parent))
            # A new case must not inherit the previous case's chosen folder.
            self.app.case_dir=self.folder/'another-case';self.app.case_dir.mkdir()
            with patch('guided_ui.sys.platform','win32'),patch('guided_ui.os.startfile',create=True) as opened:
                self.app.open_output()
            opened.assert_called_once_with(str(self.app.case_dir/'output'))

    def test_import_first_and_every_step_action_visible(self):
        self.root.geometry('900x640');self.root.update()
        for i,title in enumerate(['Import Files','Review Loads','Review Costs','Create Package']):
            self.app.go(i);self.root.update();self.assertEqual(self.app.page_title.get(),title)
            button=self.app.next_button
            self.assertTrue(button.winfo_ismapped());self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
        self.assertEqual(self.app.next_button.cget('text'),'Export COR Package')
        self.assertNotIn('address',self.app.vars)
        self.assertEqual(self.errors,[])

    def test_bid_and_finance_confirmations_invalidate_after_rate_change(self):
        self.app.vars['rate_per_cyd'].set('36')
        issues=self.app.evaluate()[3]
        self.assertTrue(any('lowest bid' in issue.lower() for issue in issues))
        self.assertTrue(any('Confirm the invoice treatment' in issue for issue in issues))

    def test_add_jpg_invoice_confirm_and_export_original_image(self):
        source=self.folder/'Vendor Invoice.jpg'
        Image.new('RGB',(600,900),'white').save(source)
        self.app.case['package_documents']=[d for d in self.app.case['package_documents'] if d['role']!='invoice']
        with patch('tkinter.filedialog.askopenfilenames',return_value=(str(source),)),patch('tkinter.messagebox.showinfo'),patch.object(self.app,'scan_photos'):
            self.app.add_document()
        self.root.update()
        def widgets(widget):
            for child in widget.winfo_children():
                yield child
                yield from widgets(child)
        confirm=next(w for w in widgets(self.root) if w.winfo_class()=='TButton' and w.cget('text')=='Confirm Document')
        confirm.invoke();self.root.update()
        invoice=next(d for d in self.app.case['package_documents'] if d['role']=='invoice')
        self.assertTrue(invoice['confirmed'])
        self.assertEqual(Path(invoice['path']).read_bytes(),source.read_bytes())
        self.app.case['financial_confirmation_hash']=financial_fingerprint(self.app.case)
        self.app.case['bid_review_confirmed']=True
        self.app.case['bid_confirmation_hash']=bid_fingerprint(self.app.case)
        self.assertEqual(self.app.evaluate()[3],[])
        with patch('tkinter.messagebox.askyesno',return_value=False),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error,patch.object(self.app,'open_output'):
            self.app.generate()
        error.assert_not_called()
        import fitz,json
        report=json.loads((self.folder/'output'/'Package_Review.json').read_text())
        section=next(s for s in report['sections'] if s['section']=='Final Invoice')
        with fitz.open(self.folder/'output'/'TEST-001_COR_PACKAGE_DRAFT.pdf') as pdf:
            self.assertTrue(pdf[section['start_page']-1].get_images())

    def test_assign_existing_image_as_financial_document_bypasses_pdf_restriction(self):
        source=self.app.case['before_photos'][0]
        self.app.selected_photo=source;self.app.slot.set('financial_pdfs')
        with patch.object(self.app,'edit_document') as editor,patch('tkinter.messagebox.showwarning') as warning:
            self.app.assign()
        editor.assert_called_once();warning.assert_not_called()
        self.assertTrue(any(d['path']==source for d in self.app.case['package_documents']))

    def test_local_ocr_updates_bid_suggestions_from_actual_source_hash(self):
        import time
        path=self.folder/'bid.jpg';Image.new('RGB',(100,100),'white').save(path)
        record=dict(path=str(path),name='bid.jpg',sha256='stale-import-hash')
        document=dict(path=str(path),name='bid.jpg',role='other',amount='',confirmed=False)
        self.app.case['package_documents']=[document];self.app.go(0)
        with patch('package_ui.read_image',return_value=('BID\nTOTAL $1,250.00','')):
            self.app.scan_photos([record]);deadline=time.monotonic()+3
            while document.get('amount')!='1250.00' and time.monotonic()<deadline:
                self.root.update();time.sleep(.01)
        self.assertEqual(document['amount'],'1250.00');self.assertFalse(document['confirmed'])
        self.assertEqual(self.app.case['photo_text_cache'][str(path)]['sha256'],file_digest(path))
        self.assertEqual(self.errors,[])

    def test_bid_review_requires_quantity_and_saves_it(self):
        self.app.go(0);self.app.documents.selection_set('1');self.app.edit_document();self.root.update()
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        widgets=list(children(self.root))
        label=next(w for w in widgets if w.winfo_class()=='TLabel' and w.cget('text')=='Debris Quantity on Bid (CYD)')
        entry=next(w for w in label.master.winfo_children() if w.winfo_class()=='TEntry')
        self.assertTrue(entry.winfo_ismapped())
        button=next(w for w in widgets if w.winfo_class()=='TButton' and w.cget('text')=='Confirm Document')
        entry.delete(0,'end')
        with patch('tkinter.messagebox.showwarning') as warning:button.invoke()
        warning.assert_called_once()
        entry.insert(0,'40');button.invoke();self.root.update()
        self.assertEqual(self.app.case['package_documents'][1]['debris_quantity_cyd'],'40')
        self.assertFalse(self.app.case['bid_review_confirmed']);self.assertEqual(self.errors,[])

    def test_add_bid_accepts_images_and_pdf_without_auto_confirmation(self):
        import fitz
        jpg=self.folder/'Unknown 1.jpg';png=self.folder/'Unknown 2.png';pdf=self.folder/'Unknown 3.pdf'
        Image.new('RGB',(400,300),'red').save(jpg);Image.new('RGB',(400,300),'green').save(png)
        doc=fitz.open();doc.new_page().insert_text((50,50),'BID\nTOTAL $2,000.00');doc.save(pdf);doc.close()
        paths=(str(jpg),str(png),str(pdf))
        with patch('tkinter.filedialog.askopenfilenames',return_value=paths),patch('tkinter.messagebox.showinfo'),patch.object(self.app,'scan_photos'):
            self.app.add_bid()
        added=[d for d in self.app.case['package_documents'] if d['name'] in {p.name for p in [jpg,png,pdf]}]
        self.assertEqual(len(added),3)
        for record in added:
            self.assertEqual(record['role'],'bid');self.assertFalse(record['confirmed'])
            original=next(p for p in [jpg,png,pdf] if p.name==record['name'])
            self.assertEqual(Path(record['path']).read_bytes(),original.read_bytes())
        self.assertFalse(self.app.case['bid_review_confirmed']);self.assertEqual(self.errors,[])

    def test_register_document_twice_does_not_duplicate_image(self):
        source=self.app.case['before_photos'][0]
        first=self.app.register_document(source);second=self.app.register_document(source)
        self.assertEqual(first,second)
        self.assertEqual(sum(d['path']==source for d in self.app.case['package_documents']),1)

    def test_old_manual_allowance_cannot_override_the_hud_rate(self):
        self.app.case.update(verified_first_10_amount='250',invoice_deduction_usd='250',invoice_amount_usd='1149.65',financial_confirmation_note='Case-specific documented allowance')
        self.app.case['financial_confirmation_hash']=financial_fingerprint(self.app.case)
        self.app.refresh();self.root.update()
        from cor_package import totals
        self.assertEqual(str(totals(self.app.case)['request']),'1049.65')
        self.assertTrue(any('deduction differs' in issue.lower() for issue in self.app.evaluate()[3]))

    def test_pdf_excludes_internal_checklist_and_footer_even_when_incomplete(self):
        from cor_package import assemble
        import fitz
        path=self.folder/'incomplete.pdf'
        assemble(self.app.case,path,['BLOCKING / INTERNAL TEST FINDING'])
        with fitz.open(path) as pdf:text='\n'.join(p.get_text() for p in pdf)
        for phrase in ['INTERNAL TEST FINDING','Human Review Required','Review Checklist','CalculatorSoup Measurement Screenshot']:
            self.assertNotIn(phrase,text)
        self.assertIn('Cubic Yard Calculation',text)
        self.assertIn('INTERNAL TEST FINDING',(self.folder/'Package_Review.json').read_text())

    def test_cost_labels_and_removed_interface_wording(self):
        def labels(widget):
            values=[]
            try:values.append(str(widget.cget('text')))
            except tk.TclError:pass
            for child in widget.winfo_children():values.extend(labels(child))
            return values
        text='\n'.join(labels(self.root))
        for phrase in ['Quantity billed','Net invoice amount','Verified allowance','GUIDED WORKSPACE','No automatic COR approval','Drafts require human review']:
            self.assertNotIn(phrase,text)
        self.assertIn('Invoice Total ($)',text)

    def test_initial_services_yes_no_shows_the_requested_question(self):
        self.app.vars['invoice_deduction_status'].set('yes');self.root.update()
        self.assertEqual(self.app.initial_services_question.get(),'HUD Deduction for the First 10 CYD')
        self.app.vars['invoice_deduction_status'].set('no');self.root.update()
        self.assertEqual(self.app.initial_services_question.get(),'HUD Deduction for the First 10 CYD')
        self.assertEqual(self.app.vars['verified_first_10_amount'].get(),'350.00')
        self.app.vars['rate_per_cyd'].set('45');self.root.update()
        self.assertEqual(self.app.vars['verified_first_10_amount'].get(),'450.00')

    def test_invoice_without_initial_services_deduction_uses_request_adjustment(self):
        self.app.case.update(invoice_deduction_status='no',invoice_deduction_usd='0',invoice_amount_usd='1399.65')
        self.app.case['financial_confirmation_hash']=financial_fingerprint(self.app.case)
        self.app.refresh();self.root.update()
        from cor_package import totals
        self.assertEqual(str(totals(self.app.case)['request']),'1049.65')
        self.assertEqual(self.app.evaluate()[3],[])

    def test_local_sorter_background_results_reach_category_review(self):
        from local_photo_sorter import LocalPhotoSorterWindow,batch,parse_prediction
        import time
        source=self.app.case['before_photos'][0]
        self.app.case['imported_files']=[dict(path=source,name='test.png',source='Synthetic')]
        model={'name':'test-local','digest':'test-v1'}
        def fake_batch(records,model,path,cancel,callback,limit):
            return batch(records,model,path,cancel,callback,limit,infer=lambda p,m:parse_prediction({'category':'invoice'}))
        with patch('local_photo_sorter.installed_models',return_value=[model]),patch('local_photo_sorter.batch',side_effect=fake_batch):
            window=LocalPhotoSorterWindow(self.app)
            deadline=time.monotonic()+3
            while not window.models and time.monotonic()<deadline:self.root.update();time.sleep(.01)
            self.assertTrue(window.models);window.start()
            while window.running and time.monotonic()<deadline:self.root.update();time.sleep(.01)
            self.assertFalse(window.running);window.poll()
            self.assertEqual(self.app.case['local_photo_results'][source]['prediction']['category'],'invoice')
            self.assertFalse(self.app.case['local_photo_results'][source]['prediction']['verified'])
            window.close()

    def test_project_saved_opened_in_temporary_workspace_and_cleanup(self):
        outer=tempfile.TemporaryDirectory();self.addCleanup(outer.cleanup)
        path=Path(outer.name)/'TEST-001.edcase'
        with patch('tkinter.filedialog.asksaveasfilename',return_value=str(path)):
            self.assertTrue(self.app.save_project())
        with patch('tkinter.filedialog.askopenfilename',return_value=str(path)):
            self.app.open_case()
        self.assertIsNotNone(self.app._case_temp)
        working=Path(self.app.case_dir)
        self.assertTrue(Path(self.app.case['loads'][0]['photos']['empty']).is_file())
        self.assertEqual(self.app.evaluate()[3],[])
        self.app.release_temporary_case()
        self.assertFalse(working.exists());self.assertTrue(path.exists())

    def test_discard_temporary_session_keeps_saved_project(self):
        outer=tempfile.TemporaryDirectory();self.addCleanup(outer.cleanup)
        path=Path(outer.name)/'saved.edcase'
        with patch('tkinter.filedialog.asksaveasfilename',return_value=str(path)):self.app.save_project()
        with patch('tkinter.filedialog.askopenfilename',return_value=str(path)):self.app.open_case()
        working=Path(self.app.case_dir);self.app.case['vendor']='Changed Vendor'
        with patch('tkinter.messagebox.askyesnocancel',return_value=False),patch.object(self.root,'destroy'):
            self.app.close_app()
        self.assertFalse(working.exists());self.assertTrue(path.exists())

    def test_temporary_session_exports_pdf_outside_working_folder(self):
        outer=tempfile.TemporaryDirectory();self.addCleanup(outer.cleanup)
        project=Path(outer.name)/'saved.edcase';pdf=Path(outer.name)/'package.pdf'
        with patch('tkinter.filedialog.asksaveasfilename',return_value=str(project)):self.app.save_project()
        with patch('tkinter.filedialog.askopenfilename',return_value=str(project)):self.app.open_case()
        with patch('tkinter.filedialog.asksaveasfilename',return_value=str(pdf)),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error:
            self.app.generate()
        error.assert_not_called();self.assertTrue(pdf.is_file())
        self.app.release_temporary_case();self.assertTrue(pdf.is_file())

    def test_cancel_project_save_keeps_temporary_session(self):
        self.app._case_temp=tempfile.TemporaryDirectory();self.addCleanup(self.app._case_temp.cleanup)
        with patch('tkinter.messagebox.askyesnocancel',return_value=True),patch('tkinter.filedialog.asksaveasfilename',return_value=''):
            self.assertFalse(self.app.prepare_leave())
        self.assertIsNotNone(self.app._case_temp)

    def test_one_button_setup_updates_sorter_without_external_installer(self):
        from local_photo_sorter import LocalPhotoSorterWindow
        import time
        ready=[False]
        def setup(cancel,progress):progress('Downloaded test assets',1,1);ready[0]=True
        with patch('local_photo_sorter.RUNTIME.ready',side_effect=lambda:ready[0]),patch('local_photo_sorter.RUNTIME.setup',side_effect=setup):
            window=LocalPhotoSorterWindow(self.app);window.setup()
            deadline=time.monotonic()+2
            while window.running and time.monotonic()<deadline:self.root.update();time.sleep(.01)
            window.poll();self.assertTrue(window.models)
            self.assertEqual(window.setup_button.cget('text'),'Photo Sorting Is Ready')
            window.close()

    def test_detected_invoice_figures_fill_empty_fields_but_require_confirmation(self):
        invoice=next(d for d in self.app.case['package_documents'] if d['role']=='invoice')
        invoice['cost_suggestions']={'invoice_amount_usd':'1149.65','invoice_quantity_cyd':'39.99'}
        self.app.case['invoice_amount_usd']=''
        self.app.refresh();self.root.update()
        self.assertEqual(self.app.vars['invoice_amount_usd'].get(),'1149.65')
        self.assertNotEqual(self.app.case['financial_confirmation_hash'],financial_fingerprint(self.app.case))
        self.app.vars['invoice_amount_usd'].set('1200');self.app.save();self.app.refresh()
        self.assertEqual(self.app.vars['invoice_amount_usd'].get(),'1200')

if __name__=='__main__':unittest.main()

