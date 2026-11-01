import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from PIL import Image
from visual_photo_review import timing_clues,apply_visual_stage,current_stage,property_review_issues,PhotoReviewWindow

class VisualEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.path=self.folder/'Before Photos_123.jpeg';Image.new('RGB',(300,200),'blue').save(self.path)
        self.case=dict(before_photos=[],during_photos=[],after_photos=[])
    def tearDown(self):self.temp.cleanup()

    def test_filename_alone_never_assigns_before(self):
        self.assertEqual(current_stage(self.case,str(self.path)),'review')
        self.assertEqual(timing_clues(self.path)['clues'],[])

    def test_date_only_has_no_invented_time_or_stage(self):
        clues=timing_clues(self.path,'2026-11-01')
        self.assertEqual(clues['clues'][0]['precision'],'Date Only')
        self.assertIsNone(clues['clues'][0]['time'])
        self.assertEqual(current_stage(self.case,str(self.path)),'review')

    def test_ocr_date_and_time_are_unverified_clues(self):
        clues=timing_clues(self.path,'2026-11-01 02:15 PM')
        self.assertEqual(clues['clues'][0]['time'],'14:15:00')
        self.assertFalse(clues['clues'][0]['verified'])

    def test_ambiguous_date_is_preserved_not_guessed(self):
        clues=timing_clues(self.path,'03/04/2026')
        self.assertEqual(clues['clues'][0]['value'],'03/04/2026')
        self.assertIsNone(clues['clues'][0]['date'])

    def test_conflicting_dates_flag_review_without_classifying_stage(self):
        exif=Image.Exif();exif[36867]='2026:11:01 10:30:00'
        Image.new('RGB',(300,200),'blue').save(self.path,exif=exif)
        clues=timing_clues(self.path,'2026-11-02 10:30:00')
        self.assertTrue(any('Differ' in flag for flag in clues['flags']))
        self.assertEqual(current_stage(self.case,str(self.path)),'review')

    def test_date_only_can_be_visually_confirmed_after(self):
        apply_visual_stage(self.case,[str(self.path)],'after',visually_checked=True)
        self.assertEqual(self.case['after_photos'],[str(self.path)])
        self.assertEqual(current_stage(self.case,str(self.path)),'after')
        self.assertEqual(property_review_issues(self.case),[])

    def test_confirmation_required_and_category_change_removes_old_phase(self):
        with self.assertRaises(ValueError):apply_visual_stage(self.case,[str(self.path)],'before')
        apply_visual_stage(self.case,[str(self.path)],'before',visually_checked=True)
        apply_visual_stage(self.case,[str(self.path)],'during',visually_checked=True)
        self.assertEqual(self.case['before_photos'],[])
        self.assertEqual(self.case['during_photos'],[str(self.path)])

    def test_changed_source_requires_review_again(self):
        apply_visual_stage(self.case,[str(self.path)],'before',visually_checked=True)
        Image.new('RGB',(301,201),'red').save(self.path)
        self.assertEqual(current_stage(self.case,str(self.path)),'review')
        self.assertTrue(property_review_issues(self.case))

    def test_legacy_assignment_needs_visual_confirmation(self):
        self.case['before_photos']=[str(self.path)]
        self.assertTrue(property_review_issues(self.case))

    def test_unreadable_file_does_not_partially_change_batch(self):
        with self.assertRaises(Exception):apply_visual_stage(self.case,[str(self.path),str(self.folder/'missing.jpg')],'after',visually_checked=True)
        self.assertEqual(self.case['after_photos'],[])

class VisualGalleryTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        from package_ui import PackageApp
        from ed_app import make_case
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.app=PackageApp(self.root)
        self.app.case=make_case('TEST-GALLERY','','Test Vendor',1,'');self.app.case_dir=self.folder
        for i in range(14):
            path=self.folder/f'Before Photos_{i}.jpg';Image.new('RGB',(300,200),(i*10,60,90)).save(path)
            self.app.case['imported_files'].append(dict(path=str(path),name=path.name,source='Synthetic Test'))
        self.app.refresh();self.root.update();self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args)
    def tearDown(self):self.root.destroy();self.temp.cleanup()

    def test_gallery_batch_visual_review_persists_and_filters(self):
        gallery=PhotoReviewWindow(self.app);self.root.update()
        self.assertEqual(len(gallery.filtered()),14)
        gallery.select_page();self.assertEqual(len(gallery.selected),12)
        gallery.target.set('Before Removal')
        with patch('tkinter.messagebox.askyesno',return_value=True):gallery.apply()
        self.assertEqual(len(self.app.case['before_photos']),12)
        gallery.filter.set('Needs Review');gallery.reset_page();self.root.update()
        self.assertEqual(len(gallery.filtered()),2)
        self.assertEqual(self.errors,[])
        import json
        saved=json.loads((self.folder/'case.json').read_text())
        self.assertEqual(len(saved['property_stage_reviews']),12)
        gallery.close()

    def test_rejected_confirmation_leaves_assignments_untouched(self):
        gallery=PhotoReviewWindow(self.app);gallery.select_page();gallery.target.set('After Removal')
        with patch('tkinter.messagebox.askyesno',return_value=False):gallery.apply()
        self.assertEqual(self.app.case['after_photos'],[])
        gallery.close()

if __name__=='__main__':unittest.main()
