import copy
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image,PngImagePlugin
from calculator_evidence import file_digest
from local_photo_sorter import MODEL_DIGEST,VERSION
from review_assist import encode_embedding,image_features
from template_review import TemplateCandidateIndex,TemplateReviewWindow,assign_template_photo,measurement_view_clues,dismiss_template_photo
from template_slot_head import predict_slots

class TemplateCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.case=dict(loads=[{'photos':{},'length_ft':'19','width_ft':'7.8','side_height_ft':'6.5','measurements_confirmed':True},{'photos':{}}],imported_files=[],local_photo_results={},before_photos=[])
        for i in range(5):self.photo(i)
    def tearDown(self):self.temp.cleanup()
    def photo(self,i):
        path=self.root/f'photo-{i}.png';pixels=np.zeros((600,300,3),np.uint8);pixels[:,:,0]=(np.arange(600)[:,None]+i*20)%255;pixels[:,:,1]=80;pixels[:,:,2]=130;Image.fromarray(pixels).save(path)
        vector=np.zeros(512);vector[i]=1
        record=dict(path=str(path),name=path.name);self.case['imported_files'].append(record)
        self.case['local_photo_results'][str(path)]=dict(sha256=file_digest(path),features=image_features(path),prediction={'embedding':encode_embedding(vector)},model_digest=MODEL_DIGEST,prompt_version=VERSION)
        return str(path)
    def index(self):
        with patch('template_review.predict_slots',return_value={'height':.8,'width':.1,'other':.1}):return TemplateCandidateIndex(self.case)
    def test_confirmed_load_beats_unreviewed_text_and_visual_scores(self):
        index=self.index();path=self.case['imported_files'][-1]['path']
        self.case['photo_load_assignments']={path:dict(load=1,sha256=file_digest(path))}
        index.scores[path]={'height':.16,'other':.1}
        index.text[self.case['imported_files'][0]['path']]={'slot':'height','load':1}
        self.assertEqual(index.shortlist(self.case,1,'height')[0][0]['path'],path)
    def test_reviewed_load_overrides_ocr_load_but_stale_review_does_not(self):
        index=self.index();path=self.case['imported_files'][-1]['path'];index.text[path]={'slot':'height','load':2};index.groups[path]=dict(load=2,vendor_load=2)
        self.case['photo_load_assignments']={path:dict(load=1,sha256=file_digest(path))}
        self.assertIn(path,{r['path'] for r in index.shortlist(self.case,1,'height',limit=20)[0]})
        self.case['photo_load_assignments'][path]['sha256']='changed'
        self.assertNotIn(path,{r['path'] for r in index.shortlist(self.case,1,'height',limit=20)[0]})
    def test_confirmed_load_keeps_uncertain_measurement_axes_available(self):
        index=self.index();path=self.case['imported_files'][-1]['path']
        index.scores[path]={'height':.11,'width':.09,'length':.08,'other':.6}
        self.case['photo_load_assignments']={path:dict(load=1,sha256=file_digest(path))}
        self.assertIn(path,{r['path'] for r in index.shortlist(self.case,1,'width',limit=20)[0]})
        self.assertNotIn(path,{r['path'] for r in index.shortlist(self.case,1,'quarter',limit=20)[0]})
    def test_other_numbered_group_is_hidden_until_browse_but_manual_correction_wins(self):
        index=self.index();path=self.case['imported_files'][0]['path'];index.groups={path:dict(load=2)}
        self.assertNotIn(path,{r['path'] for r in index.shortlist(self.case,1,'height',limit=20)[0]})
        self.assertIn(path,{r['path'] for r in index.shortlist(self.case,1,'height',browse_all=True,limit=20)[0]})
        self.case['photo_load_assignments']={path:dict(load=1,sha256=file_digest(path))}
        self.assertIn(path,{r['path'] for r in index.shortlist(self.case,1,'height',limit=20)[0]})
    def test_shortlists_do_not_assign_or_change_measurements(self):
        original=copy.deepcopy(self.case);index=self.index();rows,total=index.shortlist(self.case,1,'height')
        self.assertEqual(len(rows),3);self.assertEqual(total,5);self.assertEqual(self.case,original)
    def test_dismissal_removes_only_this_load_box_and_preserves_evidence(self):
        index=self.index();row=index.shortlist(self.case,1,'height')[0][0];original=copy.deepcopy(self.case)
        dismiss_template_photo(self.case,1,'height',row)
        self.assertNotIn(row['path'],{r['path'] for r in index.shortlist(self.case,1,'height',browse_all=True,limit=20)[0]})
        self.assertIn(row['path'],{r['path'] for r in index.shortlist(self.case,1,'width',browse_all=True,limit=20)[0]})
        self.assertIn(row['path'],{r['path'] for r in index.shortlist(self.case,2,'height',browse_all=True,limit=20)[0]})
        self.assertEqual(self.case['loads'],original['loads']);self.assertEqual(self.case['imported_files'],original['imported_files'])
    def test_changed_source_cannot_be_dismissed(self):
        row=self.index().shortlist(self.case,1,'height')[0][0];Path(row['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):dismiss_template_photo(self.case,1,'height',row)
        self.assertNotIn('template_photo_dismissals',self.case)
    def test_old_dismissal_does_not_hide_replaced_source(self):
        row=self.index().shortlist(self.case,1,'height')[0][0];dismiss_template_photo(self.case,1,'height',row)
        self.case['template_photo_dismissals']['1:height'][row['path']]['sha256']='old-source'
        self.assertIn(row['path'],{r['path'] for r in self.index().shortlist(self.case,1,'height',limit=20)[0]})
    def test_selected_photo_cannot_be_dismissed(self):
        row=self.index().shortlist(self.case,1,'height')[0][0];self.case['loads'][0]['photos']['height']=row['path']
        with self.assertRaises(ValueError):dismiss_template_photo(self.case,1,'height',row)
        self.assertEqual(self.case['loads'][0]['photos']['height'],row['path'])
    def test_other_load_measurements_require_browse_all_and_explicit_confirmation(self):
        index=self.index();p=self.case['imported_files'][0]['path'];q=self.case['imported_files'][1]['path']
        self.case['loads'][1]['photos']['height']=p
        self.case['photo_load_assignments']={q:dict(load=2,sha256=file_digest(q))}
        rows,total=index.shortlist(self.case,1,'height',limit=20)
        self.assertNotIn(p,{r['path'] for r in rows});self.assertNotIn(q,{r['path'] for r in rows})
        rows,total=index.shortlist(self.case,1,'height',browse_all=True,limit=20)
        self.assertIn(p,{r['path'] for r in rows});self.assertIn(q,{r['path'] for r in rows})
    def test_shared_measurement_needs_confirmation_and_never_copies_dimensions(self):
        path=self.case['imported_files'][0]['path'];candidate=dict(path=path,sha256=file_digest(path))
        self.case['loads'][1].update(photos={'height':path},length_ft='99')
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'height',candidate)
        assign_template_photo(self.case,1,'height',candidate,shared_container_confirmed=True)
        self.assertEqual(self.case['loads'][0]['length_ft'],'19');self.assertFalse(self.case['loads'][0]['measurements_confirmed'])
        self.assertTrue(self.case['shared_container_measurements']['1:height']['container_match_confirmed'])
    def test_sharing_cannot_reuse_progression_or_a_different_measurement_axis(self):
        path=self.case['imported_files'][0]['path'];candidate=dict(path=path,sha256=file_digest(path))
        self.case['loads'][1]['photos']['half']=path
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'half',candidate,shared_container_confirmed=True)
        self.case['loads'][1]['photos']={'width':path}
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'height',candidate,shared_container_confirmed=True)
    def test_filename_does_not_supply_a_load_number(self):
        self.case['imported_files'][0]['name']='Load 9 Height Full.png'
        rows,total=self.index().shortlist(self.case,1,'height',limit=20)
        self.assertTrue(all(r['load_clue']=='Load Not Confirmed' for r in rows))
    def test_fresh_photo_text_can_propose_without_visual_features(self):
        p=self.case['imported_files'][0]['path'];self.case['local_photo_results']={}
        self.case['photo_text_cache']={p:dict(sha256=file_digest(p),text='Load 1\nHeight: 6.5 ft')}
        index=TemplateCandidateIndex(self.case);rows,total=index.shortlist(self.case,1,'height')
        self.assertEqual([r['path'] for r in rows],[p]);self.assertEqual(rows[0]['basis'],'Photo Text Suggestion')
    def test_stale_text_does_not_supply_a_slot(self):
        p=self.case['imported_files'][0]['path'];self.case['local_photo_results']={}
        self.case['photo_text_cache']={p:dict(sha256='stale',text='Load 1\nHeight: 6.5 ft')}
        self.assertEqual(TemplateCandidateIndex(self.case).shortlist(self.case,1,'height')[0],[])
    def test_assignment_is_explicit_and_preserves_values_and_other_slots(self):
        row=self.index().shortlist(self.case,1,'height')[0][0]
        assign_template_photo(self.case,1,'height',row)
        self.assertEqual(self.case['loads'][0]['photos'],{'height':row['path']})
        self.assertEqual(self.case['loads'][0]['length_ft'],'19');self.assertFalse(self.case['loads'][0]['measurements_confirmed'])
        self.assertEqual(self.case['before_photos'],[])
        self.assertEqual(self.case['template_photo_reviews']['1:height']['sha256'],row['sha256'])
    def test_changed_candidate_does_not_mutate_selection(self):
        row=self.index().shortlist(self.case,1,'height')[0][0];Path(row['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'height',row)
        self.assertEqual(self.case['loads'][0]['photos'],{})
    def test_second_full_view_rejects_same_pixels_with_different_file_metadata(self):
        p=self.case['imported_files'][0]['path'];q=self.root/'copy.png'
        info=PngImagePlugin.PngInfo();info.add_text('note','different metadata')
        with Image.open(p) as image:image.save(q,pnginfo=info)
        self.case['imported_files'].append(dict(path=str(q)));self.case['loads'][0]['photos']['full_1']=p
        self.assertNotEqual(file_digest(p),file_digest(q))
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'full_2',dict(path=str(q),sha256=file_digest(q)))
    def test_calculation_screenshot_is_not_assigned_as_a_generic_photo(self):
        row=self.index().shortlist(self.case,1,'height')[0][0]
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'calculator',row)
    def test_browsing_supports_manual_selection_without_model_or_text(self):
        self.case['local_photo_results']={};index=TemplateCandidateIndex(self.case)
        self.assertEqual(index.shortlist(self.case,1,'height')[0],[])
        rows,total=index.shortlist(self.case,1,'height',browse_all=True);self.assertEqual(len(rows),3)
    def test_paging_keeps_distinct_candidates(self):
        index=self.index();first,total=index.shortlist(self.case,1,'height');second,_=index.shortlist(self.case,1,'height',offset=3)
        self.assertEqual(total,5);self.assertFalse({r['path'] for r in first}&{r['path'] for r in second})
    def test_feature_scores_are_finite_and_invalid_vectors_rejected(self):
        scores=predict_slots(np.ones(512));self.assertAlmostEqual(sum(scores.values()),1,places=5)
        for vector in [np.zeros(512),np.ones(3),np.full(512,np.nan)]:
            with self.assertRaises(ValueError):predict_slots(vector)
    def test_flat_blank_images_do_not_receive_visual_candidates(self):
        path=self.case['imported_files'][0]['path'];self.case['local_photo_results'][path]['features']['detail']=0
        rows,total=self.index().shortlist(self.case,1,'height',limit=20)
        self.assertNotIn(path,{r['path'] for r in rows})
    def test_tape_like_line_clues_do_not_read_or_invent_dimensions(self):
        from PIL import ImageDraw
        path=self.root/'line.png';image=Image.new('RGB',(600,400),'white');ImageDraw.Draw(image).rectangle((50,190,550,205),fill=(255,220,0));image.save(path)
        clue=measurement_view_clues(path)
        self.assertGreater(clue['horizontal'],.5);self.assertEqual(clue['vertical'],0)
        self.assertEqual(set(clue),{'horizontal','vertical'})
    def test_valid_geometry_cache_is_reused_without_image_reprocessing(self):
        p=self.case['imported_files'][0]['path'];self.case['template_geometry_cache']={p:dict(sha256=file_digest(p),version=1,horizontal=0,vertical=1)}
        with patch('template_review.measurement_view_clues',return_value={'horizontal':0,'vertical':0}) as measure:
            index=self.index()
        self.assertEqual(measure.call_count,4);self.assertEqual(index.geometry[p]['vertical'],1)
    def test_malformed_repeat_features_do_not_hide_distinct_candidates(self):
        for row in self.case['local_photo_results'].values():row['features']={'pixel_hash':'bad-identical-value'}
        rows,total=self.index().shortlist(self.case,1,'height',limit=20)
        self.assertEqual(total,5)
    def test_reviewed_financial_document_is_not_reused_as_load_photo(self):
        p=self.case['imported_files'][0]['path'];self.case['package_documents']=[dict(path=p,role='invoice',confirmed=True)]
        rows,total=self.index().shortlist(self.case,1,'height',limit=20)
        self.assertNotIn(p,{r['path'] for r in rows})
        with self.assertRaises(ValueError):assign_template_photo(self.case,1,'height',dict(path=p,sha256=file_digest(p)))

class TemplateReviewUiTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        from package_ui import PackageApp
        from ed_app import make_case
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.app=PackageApp(self.root)
        self.app.case=make_case('TEST-TEMPLATE','','Test Vendor',1,35);self.app.case_dir=self.folder
        self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        for i in range(4):
            p=self.folder/f'photo-{i}.png';Image.new('RGB',(300,650),(i*30,90,110)).save(p);vector=np.zeros(512);vector[i]=1
            self.app.case['imported_files'].append(dict(path=str(p),name=p.name))
            self.app.case.setdefault('local_photo_results',{})[str(p)]=dict(sha256=file_digest(p),prediction={'embedding':encode_embedding(vector)},model_digest=MODEL_DIGEST,prompt_version=VERSION)
        self.mock=patch('template_review.predict_slots',return_value={'height':.7,'width':.2,'other':.1});self.mock.start()
        self.app.refresh();self.root.update();self.window=TemplateReviewWindow(self.app)
        deadline=time.monotonic()+5
        while self.window.index is None and time.monotonic()<deadline:self.root.update();time.sleep(.01)
        self.assertIsNotNone(self.window.index);self.root.update()
    def tearDown(self):
        self.mock.stop();self.root.destroy();self.temp.cleanup()
    def widgets(self,parent):
        for child in parent.winfo_children():
            yield child
            yield from self.widgets(child)
    def test_using_candidate_saves_and_advances_to_next_missing_box(self):
        row=self.window.index.shortlist(self.app.case,1,'height')[0][0];self.window.use(row);self.root.update()
        saved=json.loads((self.folder/'case.json').read_text())
        self.assertEqual(saved['loads'][0]['photos']['height'],row['path']);self.assertEqual(self.window.slot(),'width')
        self.assertEqual(self.errors,[])
    def test_dismiss_and_restore_replace_suggestions_without_assigning_photos(self):
        self.window.tree.selection_set('height');self.window.reset_page();self.root.update()
        row=self.window.index.shortlist(self.app.case,1,'height')[0][0];self.window.dismiss(row);self.root.update()
        self.assertNotIn(row['path'],{r['path'] for r in self.window.index.shortlist(self.app.case,1,'height')[0]})
        self.assertEqual(self.app.case['loads'][0]['photos'],{})
        saved=json.loads((self.folder/'case.json').read_text());self.assertIn(row['path'],saved['template_photo_dismissals']['1:height'])
        self.window.restore_dismissed();self.root.update()
        self.assertIn(row['path'],{r['path'] for r in self.window.index.shortlist(self.app.case,1,'height')[0]});self.assertEqual(self.errors,[])
    def test_changed_photo_is_rejected_and_other_boxes_stay_unchanged(self):
        row=self.window.index.shortlist(self.app.case,1,'height')[0][0];Path(row['path']).write_bytes(b'changed')
        with patch('tkinter.messagebox.showwarning') as warning:self.window.use(row)
        warning.assert_called_once();self.assertEqual(self.app.case['loads'][0]['photos'],{});self.assertEqual(self.errors,[])
    def test_existing_selection_is_not_replaced_by_refresh(self):
        path=self.app.case['imported_files'][0]['path'];self.app.case['loads'][0]['photos']['height']=path
        self.window.refresh_tree('height');self.window.reset_page();self.root.update()
        self.assertEqual(self.app.case['loads'][0]['photos']['height'],path)
        self.assertEqual(self.window.tree.item('height','values'),('Selected',));self.assertEqual(self.errors,[])
    def test_three_candidate_actions_are_accessible_on_a_smaller_window(self):
        self.window.win.geometry('900x650');self.root.update();self.window.render();self.root.update()
        buttons=[w for w in self.widgets(self.window.cards) if isinstance(w,tk.ttk.Button) and w.cget('text')=='Use This Photo']
        self.assertEqual(len(buttons),self.window.PAGE_SIZE)
        navigation=[w for w in self.widgets(self.window.paging) if isinstance(w,tk.ttk.Button)]
        self.assertEqual(len(navigation),2)
        dismiss_buttons=[w for w in self.widgets(self.window.cards) if isinstance(w,tk.ttk.Button) and w.cget('text')=='Not a Match']
        self.assertEqual(len(dismiss_buttons),self.window.PAGE_SIZE)
        previews=[w for w in self.widgets(self.window.cards) if isinstance(w,tk.ttk.Label) and str(w.cget('image'))]
        self.assertTrue(previews)
        for preview in previews:self.assertTrue(preview.winfo_ismapped());self.assertGreater(preview.winfo_height(),40)
        buttons+=navigation+dismiss_buttons+[self.window.progress]
        for button in buttons:
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.window.win.winfo_rootx()+self.window.win.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.window.win.winfo_rooty()+self.window.win.winfo_height())
        self.window.tree.selection_set('first_10_proof');self.window.tree.see('first_10_proof');self.root.update()
        self.assertTrue(self.window.tree.bbox('first_10_proof'))
        self.assertEqual(self.errors,[])
    def test_container_details_uses_the_current_template_load(self):
        with patch.object(self.app,'measurements') as measurements:self.window.container_details()
        measurements.assert_called_once();self.assertEqual(self.app.e_load.get(),'1')
    def test_another_load_can_be_added_without_leaving_template_review(self):
        self.window.add_load();self.root.update()
        self.assertEqual(len(self.app.case['loads']),2);self.assertEqual(self.window.load.get(),2)
        self.assertEqual(tuple(map(str,self.window.load_box.cget('values'))),('1','2'))
        self.assertEqual(self.app.e_load.get(),'2');self.assertEqual(self.errors,[])
    def test_read_load_clues_reads_only_three_candidates_without_assigning_them(self):
        with patch('package_ui.read_image',return_value=('Load 1\nHeight: 6.5 ft','')) as read:
            self.window.read_load_clues()
            deadline=time.monotonic()+5
            while (self.app.scan_running or self.window.index is None) and time.monotonic()<deadline:self.root.update();time.sleep(.01)
        self.assertEqual(read.call_count,3)
        self.assertEqual(len(self.app.case['photo_text_cache']),3)
        self.assertEqual(self.app.case['loads'][0]['photos'],{});self.assertEqual(self.errors,[])

if __name__=='__main__':unittest.main()
