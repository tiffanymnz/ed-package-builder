"""Portable GUI integration tests. Skip on systems without a display."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from PIL import Image
from ed_app import make_case
from guided_ui import GuidedApp

class GuidedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        try: self.root = tk.Tk()
        except tk.TclError as exc: self.skipTest(str(exc))
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.temp = tempfile.TemporaryDirectory()
        self.app = GuidedApp(self.root)
        self.app.case = make_case('TEST-001', 'Test property', 'Test vendor', 1, 35)
        self.app.case_dir = Path(self.temp.name)
        self.app.case['loads'][0].update(length_ft=12, width_ft=6, side_height_ft=5)
        self.app.case.update(verified_first_10_amount='350', invoice_quantity_cyd='13.33',
            invoice_amount_usd='116.55', invoice_deduction_usd='350',
            invoice_quantity_basis='includes', invoice_deduction_status='yes',
            first_10_prior_work='no', financial_confirmation_note='Synthetic invoice')
        self.app.refresh()
        self.app.case['financial_confirmation_hash'] = self.app.finance_fingerprint()
        self.root.update()

    def tearDown(self):
        self.root.destroy(); self.temp.cleanup()

    def test_navigation_export_visible_and_no_duplicate_missing_findings(self):
        self.root.geometry('900x640'); self.root.update()
        for step in range(4):
            self.app.go(step); self.root.update()
            button = self.app.next_button
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), self.root.winfo_rootx()+self.root.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), self.root.winfo_rooty()+self.root.winfo_height())
        self.assertEqual(self.app.next_button.cget('text'), 'Generate Word draft')
        self.assertFalse(any('Source audit: Missing' in issue for issue in self.app.evaluate()[3]))
        self.assertEqual(self.errors, [])

    def test_existing_deduction_and_missing_deduction(self):
        qty, gross, deduction, issues = self.app.evaluate()
        self.assertAlmostEqual(gross-deduction, 116.55)
        self.assertFalse([issue for issue in issues if self.app.issue_step(issue) == 2])
        for key, value in [('invoice_amount_usd', '466.67'), ('invoice_deduction_usd', '0'), ('invoice_deduction_status', 'no')]:
            self.app.vars[key].set(value)
        self.assertTrue(any('Deduction missing from invoice' in issue for issue in self.app.evaluate()[3]))

    def test_photo_assignment_persistence_and_draft_export(self):
        image = self.app.case_dir/'benign-test.png'; Image.new('RGB', (100, 100), 'blue').save(image)
        self.app.case['imported_files'] = [dict(path=str(image), name=image.name, source='Synthetic test')]
        self.app.refresh(); self.app.go(1); self.root.update()
        self.app.filelist.selection_set(0); self.app.preview(); self.app.assign()
        self.assertEqual(self.app.case['loads'][0]['photos']['empty'], str(image))
        self.app.go(3)
        with patch('tkinter.messagebox.askyesno', return_value=True), patch('tkinter.messagebox.showinfo'), patch('tkinter.messagebox.showerror') as error:
            self.app.generate()
        error.assert_not_called()
        self.assertTrue((self.app.case_dir/'output'/'TEST-001_ED_Progression_DRAFT.docx').is_file())
        import json
        self.assertEqual(json.loads((self.app.case_dir/'case.json').read_text())['loads'][0]['photos']['empty'], str(image))
        self.assertEqual(self.errors, [])

if __name__ == '__main__': unittest.main()
