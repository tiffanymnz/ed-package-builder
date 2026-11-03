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

    def test_changed_contents_with_identical_size_and_timestamp_need_review(self):
        import os
        Image.new('RGB',(100,100),'blue').save(self.path,format='BMP')
        apply_visual_stage(self.case,[str(self.path)],'before',visually_checked=True)
        stat=self.path.stat()
        Image.new('RGB',(100,100),'red').save(self.path,format='BMP')
        os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertEqual(self.path.stat().st_size,stat.st_size)
        self.assertEqual(self.path.stat().st_mtime_ns,stat.st_mtime_ns)
        self.assertEqual(current_stage(self.case,str(self.path)),'review')
        self.assertTrue(property_review_issues(self.case))

    def test_unreadable_file_does_not_partially_change_batch(self):
        with self.assertRaises(Exception):apply_visual_stage(self.case,[str(self.path),str(self.folder/'missing.jpg')],'after',visually_checked=True)
        self.assertEqual(self.case['after_photos'],[])

    def test_windows_source_folder_group_is_platform_independent(self):
        from types import SimpleNamespace
        gallery=SimpleNamespace(group_by=SimpleNamespace(get=lambda:'Source Folder'))
        self.assertEqual(PhotoReviewWindow.group_key(gallery,dict(path=str(self.path),source=r'C:\Vendor\Load 1\image.jpg')),'C:/Vendor/Load 1')

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

    def category_controls(self,gallery):
        gallery.correct_category();self.root.update()
        dialog=next(w for w in gallery.win.winfo_children() if isinstance(w,tk.Toplevel))
        def walk(parent):
            for child in parent.winfo_children():
                yield child
                yield from walk(child)
        widgets=list(walk(dialog))
        combo=next(w for w in widgets if isinstance(w,tk.ttk.Combobox))
        save=next(w for w in widgets if isinstance(w,tk.ttk.Button) and w.cget('text')=='Save Category')
        remove=next(w for w in widgets if isinstance(w,tk.ttk.Button) and w.cget('text')=='Remove Saved Category')
        return dialog,combo,save,remove

    def test_category_correction_persists_without_assigning_load_or_stage(self):
        gallery=PhotoReviewWindow(self.app);path=self.app.case['imported_files'][0]['path'];gallery.selected={path}
        dialog,combo,save,remove=self.category_controls(gallery);combo.set('Document / Receipt')
        with patch('tkinter.messagebox.askyesno',return_value=True):save.invoke()
        self.assertEqual(self.app.case['photo_category_examples'][path]['category'],'documents')
        self.assertEqual(gallery.suggestion_index[path],'Documents (Confirm Purpose)')
        self.assertEqual(self.app.case['before_photos'],[]);self.assertEqual(self.app.case['loads'][0]['photos'],{})
        gallery.selected={path};dialog,combo,save,remove=self.category_controls(gallery);remove.invoke()
        self.assertNotIn(path,self.app.case['photo_category_examples'])
        self.assertEqual(self.errors,[]);gallery.close()

    def test_category_dialog_rejects_photo_changed_after_it_opened(self):
        gallery=PhotoReviewWindow(self.app);path=self.app.case['imported_files'][0]['path'];gallery.selected={path}
        dialog,combo,save,remove=self.category_controls(gallery);combo.set('Document / Receipt');Path(path).write_bytes(b'changed')
        with patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showerror') as error:save.invoke()
        error.assert_called_once();self.assertFalse(self.app.case.get('photo_category_examples'))
        self.assertEqual(self.errors,[]);gallery.close()

    def test_category_conflict_requires_rechecking_existing_property_stage(self):
        from review_assist import confirm_categories
        from calculator_evidence import file_digest
        path=self.app.case['imported_files'][0]['path']
        apply_visual_stage(self.app.case,[path],'before',visually_checked=True)
        confirm_categories(self.app.case,[path],'documents',{path:{'sha256':file_digest(path)}})
        self.assertEqual(current_stage(self.app.case,path),'review')
        self.assertTrue(any('category conflict' in issue for issue in property_review_issues(self.app.case)))
        with self.assertRaises(ValueError):apply_visual_stage(self.app.case,[path],'after',visually_checked=True)

    def test_case_examples_update_unclear_gallery_groups(self):
        from review_assist import encode_embedding,confirm_categories
        from calculator_evidence import file_digest
        from local_photo_sorter import MODEL_DIGEST,VERSION
        import numpy as np
        records=self.app.case['imported_files'];v=np.zeros(512);v[0]=1;w=np.zeros(512);w[1]=1
        rows={r['path']:dict(sha256=file_digest(r['path']),model_digest=MODEL_DIGEST,prompt_version=VERSION,prediction={'category':'unclear','embedding':encode_embedding(w if i==1 else v)}) for i,r in enumerate(records)}
        self.app.case['local_photo_results']=rows
        confirm_categories(self.app.case,[records[0]['path']],'property_photos',rows)
        confirm_categories(self.app.case,[records[1]['path']],'documents',rows)
        gallery=PhotoReviewWindow(self.app)
        target=records[2]['path'];self.assertEqual(gallery.suggestion_index[target],'Property Photos')
        self.assertEqual(gallery.assistance['categories'][target]['basis'],'From Your Examples')
        self.assertEqual(self.app.case['before_photos'],[]);gallery.close()

    def test_find_similar_photos_groups_and_ranks_without_assignments(self):
        from review_assist import encode_embedding
        from calculator_evidence import file_digest
        from local_photo_sorter import MODEL_DIGEST,VERSION
        import numpy as np
        records=self.app.case['imported_files'];vector=np.zeros(512);vector[0]=1
        other=np.zeros(512);other[1]=1
        self.app.case['local_photo_results']={r['path']:dict(sha256=file_digest(r['path']),model_digest=MODEL_DIGEST,prompt_version=VERSION,prediction={'category':'property_photos','embedding':encode_embedding(vector if i<5 else other)}) for i,r in enumerate(records)}
        gallery=PhotoReviewWindow(self.app);gallery.selected={records[0]['path']};gallery.find_similar()
        self.assertEqual(len(gallery.filtered()),5)
        gallery.select_group();self.assertEqual(len(gallery.selected),5)
        self.assertEqual(self.app.case['before_photos'],[])
        self.assertEqual(self.app.case['loads'][0]['photos'],{})
        self.assertEqual(self.errors,[]);gallery.close()

    def test_changed_anchor_is_not_used_for_similarity(self):
        from review_assist import encode_embedding
        from calculator_evidence import file_digest
        from local_photo_sorter import MODEL_DIGEST,VERSION
        import numpy as np
        record=self.app.case['imported_files'][0];path=record['path'];vector=np.ones(512)
        self.app.case['local_photo_results']={path:dict(sha256=file_digest(path),model_digest=MODEL_DIGEST,prompt_version=VERSION,prediction={'embedding':encode_embedding(vector)})}
        gallery=PhotoReviewWindow(self.app);gallery.selected={path};Path(path).write_bytes(b'changed')
        with patch('tkinter.messagebox.showinfo') as info:gallery.find_similar()
        info.assert_called_once();self.assertFalse(gallery.similarity_scores)
        self.assertEqual(self.app.case['loads'][0]['photos'],{});gallery.close()

    def test_gallery_batch_visual_review_persists_and_filters(self):
        gallery=PhotoReviewWindow(self.app);gallery.page_size.set(12);gallery.change_size();self.root.update()
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

    def test_group_selection_spans_pages_and_source_groups_do_not_assign_stage(self):
        for i,record in enumerate(self.app.case['imported_files']):record['source']=f'/vendor/group_{i%2}/photo.jpg'
        gallery=PhotoReviewWindow(self.app);gallery.page_size.set(12);gallery.change_size()
        gallery.select_group();self.assertEqual(len(gallery.selected),14)
        gallery.clear_selection();gallery.group_by.set('Source Folder');gallery.update_groups()
        gallery.group.set('/vendor/group_1');gallery.reset_page();gallery.select_group()
        self.assertEqual(len(gallery.selected),7)
        self.assertTrue(all(current_stage(self.app.case,p)=='review' for p in gallery.selected))
        gallery.close()

    def test_thousand_photo_group_uses_paged_thumbnails(self):
        records=self.app.case['imported_files'];seed=Path(records[0]['path']).read_bytes()
        for i in range(14,1000):
            path=self.folder/f'photo_{i}.jpg';path.write_bytes(seed)
            records.append(dict(path=str(path),name=path.name,source=f'/vendor/day_{i%10}/photo.jpg'))
        gallery=PhotoReviewWindow(self.app);self.root.update()
        self.assertEqual(len(gallery.filtered()),1000)
        self.assertEqual(len(gallery.images),24)
        gallery.group_by.set('Source Folder');gallery.update_groups();gallery.group.set('/vendor/day_9');gallery.reset_page();gallery.select_group()
        self.assertEqual(len(gallery.selected),99)
        self.assertLessEqual(len(gallery.images),24)
        gallery.close()

    def test_best_shots_expand_all_originals_and_preserve_evidence(self):
        from review_assist import image_features
        from calculator_evidence import file_digest
        from local_photo_sorter import MODEL_DIGEST,VERSION
        records=self.app.case['imported_files'];seed=Path(records[0]['path']).read_bytes()
        for record in records[:3]:Path(record['path']).write_bytes(seed)
        self.app.case['local_photo_results']={r['path']:dict(sha256=file_digest(r['path']),features=image_features(r['path']),model_digest=MODEL_DIGEST,prompt_version=VERSION,prediction={'category':'property_photos'}) for r in records}
        self.app.case['loads'][0]['photos']['empty']=records[0]['path']
        gallery=PhotoReviewWindow(self.app);gallery.best_only.set(True);gallery.reset_page();self.root.update()
        self.assertEqual(len(gallery.filtered()),12)
        self.assertIn(records[0]['path'],[r['path'] for r in gallery.filtered()])
        gallery.show_repeat_set(records[0]['path'])
        self.assertEqual(len(gallery.filtered()),3)
        self.assertTrue(all(Path(r['path']).exists() for r in records))
        self.assertEqual(self.errors,[]);gallery.close()

    def test_manual_load_album_works_before_analysis_without_filling_slots(self):
        gallery=PhotoReviewWindow(self.app);gallery.select_page();gallery.load_choice.set('1')
        with patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showerror') as error:gallery.assign_load()
        error.assert_not_called()
        self.assertEqual(len(self.app.case['photo_load_assignments']),14)
        self.assertEqual(self.app.case['loads'][0]['photos'],{})
        self.assertEqual(self.errors,[]);gallery.close()

if __name__=='__main__':unittest.main()
