import copy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image,PngImagePlugin
from calculator_evidence import file_digest
from loading_sequence import propose_loading_sequence,apply_loading_sequence
from template_review import assign_template_photo
from evidence_audit import collect,reviewed_source_conflicts,loading_photo_conflicts

class SequenceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.paths=[];self.case=dict(loads=[{'photos':{},'length_ft':'12','width_ft':'6','side_height_ft':'5','measurements_confirmed':True}],imported_files=[])
  for i in range(8):
   p=Path(self.temp.name)/f'{i}.png';Image.new('RGB',(100,80),(i*25,80,90)).save(p);self.paths.append(str(p));self.case['imported_files'].append(dict(path=str(p)))
 def tearDown(self):self.temp.cleanup()
 def candidate(self,i):return dict(path=self.paths[i],sha256=file_digest(self.paths[i]),name=str(i),basis='Visual Candidate',reviewed_load_match=True)
 def index(self,scores,options):
  index=SimpleNamespace(scores={self.paths[i]:s for i,s in scores.items()})
  index.shortlist=lambda case,n,slot,**kwargs:([self.candidate(i) for i in options.get(slot,[])],len(options.get(slot,[])))
  return index
 def test_proposal_is_nonmutating_and_never_reuses_photo(self):
  index=self.index({0:dict(empty=.7,quarter=.1),1:dict(full=.8),2:dict(full=.6)},dict(empty=[0],quarter=[0],half=[1,2],full_1=[1,2],full_2=[1,2]));before=copy.deepcopy(self.case)
  plan=propose_loading_sequence(self.case,index,1);selected=[r['candidate']['path'] for r in plan.values() if r['candidate']]
  self.assertEqual(len(selected),len(set(selected)));self.assertIsNone(plan['quarter']['candidate']);self.assertIsNone(plan['half']['candidate']);self.assertEqual(self.case,before)
 def test_current_choices_are_pinned(self):
  self.case['loads'][0]['photos']['quarter']=self.paths[0]
  plan=propose_loading_sequence(self.case,self.index({0:dict(empty=.9)},dict(empty=[0])),1)
  self.assertTrue(plan['quarter']['current']);self.assertIsNone(plan['empty']['candidate'])
 def test_no_fabricated_second_full_view(self):
  plan=propose_loading_sequence(self.case,self.index({1:dict(full=.8)},dict(full_1=[1],full_2=[1])),1)
  self.assertEqual(sum(bool(plan[s]['candidate']) for s in ('full_1','full_2')),1)
 def test_duplicate_assignment_is_rejected(self):
  assign_template_photo(self.case,1,'quarter',self.candidate(0));before=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):assign_template_photo(self.case,1,'half',self.candidate(0))
  self.assertEqual(self.case,before)
 def test_reencoded_identical_pixels_are_rejected(self):
  info=PngImagePlugin.PngInfo();info.add_text('test','different metadata')
  with Image.open(self.paths[0]) as im:im.save(self.paths[1],pnginfo=info)
  assign_template_photo(self.case,1,'quarter',self.candidate(0))
  with self.assertRaises(ValueError):assign_template_photo(self.case,1,'half',self.candidate(1))
 def test_atomic_failure_when_second_file_changes(self):
  selections=dict(quarter=self.candidate(0),half=self.candidate(1));before=copy.deepcopy(self.case);Image.new('RGB',(100,80),'red').save(self.paths[1])
  with self.assertRaises(ValueError):apply_loading_sequence(self.case,1,selections)
  self.assertEqual(self.case,before)
 def test_atomic_swap_preserves_measurements(self):
  self.case['loads'][0]['photos']=dict(quarter=self.paths[0],half=self.paths[1]);apply_loading_sequence(self.case,1,dict(quarter=self.candidate(1),half=self.candidate(0)))
  self.assertEqual(self.case['loads'][0]['photos'],dict(quarter=self.paths[1],half=self.paths[0]));self.assertTrue(self.case['loads'][0]['measurements_confirmed'])
 def test_explicit_clear_and_move(self):
  self.case['loads'][0]['photos']=dict(quarter=self.paths[0]);apply_loading_sequence(self.case,1,dict(quarter=None,half=self.candidate(0)));self.assertEqual(self.case['loads'][0]['photos'],dict(half=self.paths[0]))
 def test_changed_confirmed_photo_invalidates_review(self):
  assign_template_photo(self.case,1,'half',self.candidate(0));self.assertEqual(reviewed_source_conflicts(self.case),[])
  Image.new('RGB',(100,80),'red').save(self.paths[0]);self.assertEqual(len(reviewed_source_conflicts(self.case)),1)
 def test_reviewed_shared_dimensions_pass_cross_load_audit(self):
  self.case['loads'].append({'photos':{}});assign_template_photo(self.case,1,'height',self.candidate(0));assign_template_photo(self.case,2,'height',self.candidate(0),shared_container_confirmed=True)
  self.assertFalse(any(r['type']=='cross_load_reuse' for r in collect(self.case)['issues']))
  self.case['shared_container_measurements']['2:height']['sha256']='stale'
  self.assertTrue(any(r['type']=='cross_load_reuse' for r in collect(self.case)['issues']))
 def test_legacy_stage_duplicates_are_reported_at_export(self):
  self.case['loads'][0]['photos']=dict(quarter=self.paths[0],half=self.paths[0]);self.assertEqual(len(loading_photo_conflicts(self.case)),1)

class DocumentFreshnessTests(unittest.TestCase):
 def test_changed_invoice_invalidates_finance_and_bid_review(self):
  from test_cor_package import fixture
  from cor_package import financial_fingerprint,bid_fingerprint,validate
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));doc=case['package_documents'][0];doc['reviewed_sha256']=file_digest(doc['path']);finance=financial_fingerprint(case);bid=bid_fingerprint(case)
   Path(doc['path']).write_bytes(b'changed invoice')
   self.assertNotEqual(finance,financial_fingerprint(case));self.assertNotEqual(bid,bid_fingerprint(case));self.assertTrue(any('Document changed after review' in issue for issue in validate(case)))

class SequenceUiTests(unittest.TestCase):
 def setUp(self):
  import tkinter as tk
  from tkinter import ttk
  from unittest.mock import Mock
  try:self.root=tk.Tk()
  except tk.TclError as exc:self.skipTest(str(exc))
  self.root.geometry('1000x740');self.temp=tempfile.TemporaryDirectory();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
  self.case=dict(loads=[{'photos':{}}],imported_files=[])
  self.candidates=[]
  for i in range(6):
   path=Path(self.temp.name)/f'{i}.png';Image.new('RGB',(300,200),(i*30,80,90)).save(path);self.case['imported_files'].append(dict(path=str(path)));self.candidates.append(dict(path=str(path),sha256=file_digest(path),basis='Visual Candidate'))
  from loading_sequence import STAGES,LoadingSequenceWindow
  index=SimpleNamespace(scores={r['path']:{'full' if stage.startswith('full_') else stage:.8} for (stage,_),r in zip(STAGES,self.candidates)})
  index.shortlist=lambda case,n,slot,**kwargs:([self.candidates[next(i for i,(s,_) in enumerate(STAGES) if s==slot)]],1)
  app=SimpleNamespace(root=self.root,ui_font='Arial',case=self.case,e_load=tk.StringVar(value='1'),save=Mock())
  self.parent=SimpleNamespace(app=app,case=self.case,win=self.root,load=tk.IntVar(value=1),index=index,refresh=Mock())
  self.window=LoadingSequenceWindow(self.parent);self.root.update()
 def tearDown(self):self.root.destroy();self.temp.cleanup()
 def test_all_six_stages_visible_and_nothing_prechecked(self):
  self.assertEqual(len(self.window.grid.winfo_children()),6);self.assertFalse(any(v.get() for v in self.window.flags.values()));self.assertIn('disabled',self.window.save_button.state())
  for card in self.window.grid.winfo_children():
   self.assertLessEqual(card.winfo_rooty()+card.winfo_height(),self.window.win.winfo_rooty()+self.window.win.winfo_height())
  self.assertEqual(self.errors,[])
 def test_only_checked_choices_are_saved_in_one_action(self):
  self.window.flags['empty'].set(True);self.window.flags['half'].set(True);self.window.apply();self.root.update()
  self.assertEqual(set(self.case['loads'][0]['photos']),{'empty','half'});self.parent.app.save.assert_called_once();self.assertEqual(self.errors,[])
 def test_case_change_does_not_write_to_new_case(self):
  before=copy.deepcopy(self.case);self.window.flags['half'].set(True);self.parent.app.case={'loads':[]};self.window.apply();self.assertEqual(self.case,before);self.parent.app.save.assert_not_called()
 def test_changing_alternative_clears_its_confirmation(self):
  self.window.flags['half'].set(True);self.window.choose('half',self.candidates[2]);self.assertFalse(self.window.flags['half'].get());self.assertEqual(self.errors,[])

 def test_visual_alternatives_do_not_assign_before_checked_save(self):
  before=copy.deepcopy(self.case);self.window.other('half');self.root.update();picker=self.window.picker
  self.assertTrue(picker.options);picker.choose(picker.options[0]);self.root.update()
  self.assertEqual(self.case,before);self.assertFalse(self.window.flags['half'].get());self.assertTrue(picker.closed);self.assertEqual(self.errors,[])
