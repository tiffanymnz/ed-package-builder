import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from calculator_evidence import file_digest
from load_identity import text_numbers,card_candidate
from load_groups import confirm_card,propose_groups
from photo_semantics import measurement_relevance,stage_suggestion

class ClueTests(unittest.TestCase):
 def test_circled_and_inline_numbers_without_dimension_guessing(self):
  self.assertEqual(text_numbers('Truck ① Load ②'),[2]);self.assertEqual(text_numbers('Load (4)'),[4])
  self.assertEqual(text_numbers('Truck (1) Load (2)\nTruck (1) Load (3)'),[2,3])
  self.assertEqual(text_numbers('Load 2 18 x 8 x 5'),[]);self.assertEqual(text_numbers('The invoice for load 3 is paid'),[])
 def test_white_label_is_a_candidate_without_requiring_good_ocr(self):
  from PIL import ImageDraw
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'label.png';im=Image.new('RGB',(600,400),'#aaaaaa');draw=ImageDraw.Draw(im)
   for y in range(70,260,40):draw.text((50,y),'TRUCK 1 LOAD 2',fill='black',font_size=32)
   im.save(p);self.assertTrue(card_candidate(p,'unreadable'))
 def test_irrelevant_measurements_are_withheld(self):
  values=dict(container_measurement=.25,grass_measurement=.32,bin_interior=.2,load_board=.2,pointing_hand=.2)
  self.assertFalse(measurement_relevance(values))
  values.update(grass_measurement=.20,pointing_hand=.29)
  self.assertFalse(measurement_relevance(values));self.assertTrue(measurement_relevance(values,{'horizontal':.8}))
 def test_stage_clue_is_not_an_assignment_or_a_date_rule(self):
  v=dict(before=.33,after=.28)
  self.assertEqual(stage_suggestion(v,'property_photos')['stage'],'before');self.assertIsNone(stage_suggestion(v,'container_photos'))
  self.assertIsNone(stage_suggestion(dict(before=.28,after=.279),'property_photos'))

class GroupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.case=dict(loads=[{'photos':{}}],imported_files=[],local_photo_results={})
  self.paths=[]
  for i in range(4):
   p=self.root/f'{i}.png';Image.new('RGB',(50,50),(i*30,80,90)).save(p);path=str(p);self.paths.append(path);self.case['imported_files'].append(dict(path=path));self.case['local_photo_results'][path]=dict(sha256=file_digest(path))
  self.values=dict(load_board=.19,loaded_container=.32,empty_container=.29,container_measurement=.28,property=.20,grass_measurement=.17,bin_interior=.18,pointing_hand=.18,receipt=.2)
 def tearDown(self):self.temp.cleanup()
 def rows(self):return [dict(path=p,sha256=file_digest(p),category='container_photos',load=None,stage='review') for p in self.paths]
 def test_reviewed_cards_without_clock_bounds_do_not_group_by_file_order(self):
  confirm_card(self.case,self.paths[0],1);confirm_card(self.case,self.paths[2],2);before=copy.deepcopy(self.case)
  with patch('load_groups.scores',return_value=self.values):groups=propose_groups(self.case,self.rows())
  self.assertEqual(set(groups),{self.paths[0],self.paths[2]});self.assertEqual(groups[self.paths[0]]['load'],1);self.assertEqual(groups[self.paths[2]]['load'],2);self.assertEqual(self.case,before);self.assertNotIn('photo_load_assignments',self.case)
 def test_no_group_before_a_card_and_stale_card_is_ignored(self):
  confirm_card(self.case,self.paths[2],1)
  with patch('load_groups.scores',return_value=self.values):groups=propose_groups(self.case,self.rows())
  self.assertNotIn(self.paths[1],groups)
  Image.new('RGB',(50,50),'red').save(self.paths[2])
  with patch('load_groups.scores',return_value=self.values):self.assertEqual(propose_groups(self.case,self.rows()),{})
 def test_human_assignments_and_financial_documents_are_protected(self):
  confirm_card(self.case,self.paths[0],1);rows=self.rows();rows[1]['load']=2
  self.case['package_documents']=[dict(path=self.paths[3],role='invoice',confirmed=True)]
  with patch('load_groups.scores',return_value=self.values):groups=propose_groups(self.case,rows)
  self.assertNotIn(self.paths[1],groups);self.assertNotIn(self.paths[3],groups)
 def test_changed_card_cannot_be_confirmed(self):
  Image.new('RGB',(50,50),'red').save(self.paths[0])
  with self.assertRaises(ValueError):confirm_card(self.case,self.paths[0],1)
  self.assertNotIn('load_card_reviews',self.case)

class CardUiTests(unittest.TestCase):
 def test_card_review_keeps_typed_number_on_background_updates(self):
  import tkinter as tk
  from package_ui import PackageApp
  from ed_app import make_case
  from load_card_review import CardReviewWindow
  try:root=tk.Tk()
  except tk.TclError as exc:self.skipTest(str(exc))
  try:
   with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'card.png';Image.new('RGB',(400,300),'white').save(path)
    app=PackageApp(root);app.case=make_case('UI','','Vendor',1,35);app.case_dir=Path(folder);app.start_photo_work=lambda:None
    row=dict(path=str(path),name='Card',sha256=file_digest(path),reviewed_load=None,options=[])
    app.case['imported_files']=[row];app.case['local_photo_results']={str(path):dict(sha256=row['sha256'])}
    with patch('load_card_review.card_candidates',return_value=[row]):
     win=CardReviewWindow(app);root.update();win.number.set('4');win.refresh(preserve=True);root.update();self.assertEqual(win.number.get(),'4');win.close()
  finally:root.destroy()
 def test_stale_preview_cannot_confirm_a_changed_card(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'card.png';Image.new('RGB',(100,100),'white').save(path);old=file_digest(path)
   Image.new('RGB',(100,100),'red').save(path);case=dict(loads=[{'photos':{}}],imported_files=[dict(path=str(path))],local_photo_results={str(path):dict(sha256=file_digest(path))})
   with self.assertRaises(ValueError):confirm_card(case,str(path),1,expected_sha=old)
