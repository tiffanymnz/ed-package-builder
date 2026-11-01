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
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=PackageApp(self.root)
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

    def test_complete_export_through_actual_app(self):
        self.assertEqual(self.app.evaluate()[3],[])
        with patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error,patch.object(self.app,'open_output'):
            self.app.generate()
        error.assert_not_called()
        self.assertTrue((self.folder/'output'/'TEST-001_COR_PACKAGE_DRAFT.pdf').is_file())
        self.assertIn('$1,099.65',(self.folder/'output'/'COR_Request_Description.txt').read_text())

    def test_import_first_and_every_step_action_visible(self):
        self.root.geometry('900x640');self.root.update()
        for i,title in enumerate(['Import Files','Review Loads','Review Costs','Create Package']):
            self.app.go(i);self.root.update();self.assertEqual(self.app.page_title.get(),title)
            button=self.app.next_button
            self.assertTrue(button.winfo_ismapped());self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),900)
        self.assertEqual(self.app.next_button.cget('text'),'Export COR Package')
        self.assertNotIn('address',self.app.vars)
        self.assertEqual(self.errors,[])

    def test_bid_and_finance_confirmations_invalidate_after_rate_change(self):
        self.app.vars['rate_per_cyd'].set('36')
        issues=self.app.evaluate()[3]
        self.assertTrue(any('lowest bid' in issue.lower() for issue in issues))
        self.assertTrue(any('Financial rule not confirmed' in issue for issue in issues))

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
        self.app.case['bid_review_confirmed']=True
        self.app.case['bid_confirmation_hash']=bid_fingerprint(self.app.case)
        self.assertEqual(self.app.evaluate()[3],[])
        with patch('tkinter.messagebox.askyesno',return_value=False),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error,patch.object(self.app,'open_output'):
            self.app.generate()
        error.assert_not_called()
        import fitz,json
        report=json.loads((self.folder/'output'/'Package_Review.json').read_text())
        section=next(s for s in report['sections'] if s['section']=='Vendor Invoice')
        with fitz.open(self.folder/'output'/'TEST-001_COR_PACKAGE_DRAFT.pdf') as pdf:
            self.assertTrue(pdf[section['start_page']-1].get_images())

    def test_assign_existing_image_as_financial_document_bypasses_pdf_restriction(self):
        source=self.app.case['before_photos'][0]
        self.app.selected_photo=source;self.app.slot.set('financial_pdfs')
        with patch.object(self.app,'edit_document') as editor,patch('tkinter.messagebox.showwarning') as warning:
            self.app.assign()
        editor.assert_called_once();warning.assert_not_called()
        self.assertTrue(any(d['path']==source for d in self.app.case['package_documents']))

    def test_register_document_twice_does_not_duplicate_image(self):
        source=self.app.case['before_photos'][0]
        first=self.app.register_document(source);second=self.app.register_document(source)
        self.assertEqual(first,second)
        self.assertEqual(sum(d['path']==source for d in self.app.case['package_documents']),1)

if __name__=='__main__':unittest.main()
