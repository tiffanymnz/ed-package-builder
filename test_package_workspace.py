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

if __name__=='__main__':unittest.main()
