import copy,json,random,tempfile,unittest
from pathlib import Path
from PIL import Image
from load_identity import VERSION
from load_text_runtime import MODEL_DIGEST
from calculator_evidence import file_digest
from load_groups import propose_groups

class EvidenceGroupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.case=dict(loads=[{'photos':{}},{'photos':{}}],imported_files=[],load_identity_cache={});self.rows=[]
  for i in range(6):
   p=str(Path(self.tmp.name)/f'{i}.png');Image.new('RGB',(80,60),(i*30,90,80)).save(p);sha=file_digest(p);self.case['imported_files'].append(dict(path=p));self.rows.append(dict(path=p,sha256=sha,load=None,stage='review',category='container_photos',sequence_time=f'2026-10-05T10:{i*5:02}:00',sequence_source='photo_text'))
  self.card(0,7);self.card(4,7)
 def tearDown(self):self.tmp.cleanup()
 def card(self,i,n):
  row=self.rows[i];self.case['load_identity_cache'][row['path']]=dict(version=VERSION,model_digest=MODEL_DIGEST,sha256=row['sha256'],options=[n],status='single_reader',readings=[dict(engine='florence',loads=[n],text=f'LOAD {n}')])
 def map(self,i,n):
  row=self.rows[i];self.case.setdefault('load_card_reviews',{})[row['path']]=dict(confirmed=True,sha256=row['sha256'],load=n)
 def test_explicit_vendor_number_does_not_guess_package_number(self):
  out=propose_groups(self.case,self.rows);self.assertIsNone(out[self.rows[2]['path']]['load']);self.assertEqual(out[self.rows[2]['path']]['vendor_load'],7)
 def test_one_review_maps_matching_cards_without_assigning_case_photos(self):
  self.map(0,1);before=copy.deepcopy(self.case);out=propose_groups(self.case,self.rows);self.assertEqual(out[self.rows[2]['path']]['load'],1);self.assertEqual(self.case,before)
 def test_shuffled_and_reversed_files_do_not_change_membership(self):
  self.map(0,1);expected=propose_groups(self.case,self.rows)
  for seed in [1,47,48]:
   c=copy.deepcopy(self.case);rows=list(self.rows);random.Random(seed).shuffle(c['imported_files']);random.Random(seed).shuffle(rows);self.assertEqual(propose_groups(c,rows),expected)
 def test_date_only_cards_do_not_propagate(self):
  for r in self.rows:r['sequence_time']='2026-10-05'
  out=propose_groups(self.case,self.rows);self.assertNotIn(self.rows[2]['path'],out);self.assertEqual(len(out),2)
 def test_no_extrapolation_past_last_card(self):self.assertNotIn(self.rows[5]['path'],propose_groups(self.case,self.rows))
 def test_foreign_card_inside_window_blocks_time_inference(self):
  self.card(2,8);self.assertNotIn(self.rows[1]['path'],propose_groups(self.case,self.rows))
 def test_conflicting_package_mappings_do_not_propagate_number(self):
  self.map(0,1);self.map(4,2);out=propose_groups(self.case,self.rows);self.assertEqual(out[self.rows[0]['path']]['load'],1);self.assertEqual(out[self.rows[4]['path']]['load'],2);self.assertTrue(out[self.rows[0]['path']]['cross_source_conflict']);self.assertNotIn(self.rows[2]['path'],out)
 def test_source_changed_after_reading_cannot_anchor(self):
  Image.new('RGB',(80,60),'red').save(self.rows[0]['path']);self.assertNotIn(self.rows[2]['path'],propose_groups(self.case,self.rows))
 def test_human_category_and_property_stage_are_preserved(self):
  self.rows[2]['stage']='during';self.case['photo_category_examples']={self.rows[1]['path']:dict(sha256=self.rows[1]['sha256'],category='property_photos')};out=propose_groups(self.case,self.rows);self.assertNotIn(self.rows[1]['path'],out);self.assertNotIn(self.rows[2]['path'],out)
 def test_receipts_do_not_acquire_load_from_time_alone(self):
  self.rows[2]['category']='documents';self.assertNotIn(self.rows[2]['path'],propose_groups(self.case,self.rows))
 def test_numeric_answer_without_visible_load_text_is_not_anchor(self):
  self.case['load_identity_cache'][self.rows[0]['path']]['readings'][0]['text']='7';self.assertNotIn(self.rows[2]['path'],propose_groups(self.case,self.rows))
 def test_known_financial_document_is_never_card_group(self):
  self.case['package_documents']=[dict(path=self.rows[0]['path'],confirmed=True,role='invoice')];self.assertNotIn(self.rows[0]['path'],propose_groups(self.case,self.rows))

 def test_reviewed_card_number_can_correct_reader_without_editing_prediction(self):
  from load_groups import confirm_card
  self.case['local_photo_results']={r['path']:dict(sha256=r['sha256']) for r in self.rows}
  original=copy.deepcopy(self.case['load_identity_cache'])
  confirm_card(self.case,self.rows[0]['path'],1,vendor_number=9)
  out=propose_groups(self.case,self.rows)
  self.assertEqual(out[self.rows[0]['path']]['vendor_load'],9);self.assertEqual(out[self.rows[0]['path']]['load'],1)
  self.assertEqual(self.case['load_identity_cache'],original)

class PrintedClockTests(unittest.TestCase):
 def test_at_between_printed_date_and_clock_is_supported(self):
  from visual_photo_review import timing_clues
  from load_identity import explicit_clock
  out=timing_clues('missing.jpg','Thursday, September 10, 2026 at 10:43 AM')
  self.assertEqual(out['clues'][0]['time'],'10:43:00');self.assertTrue(explicit_clock(out['clues'][0]))
 def test_date_without_time_stays_date_only(self):
  from visual_photo_review import timing_clues
  self.assertIsNone(timing_clues('missing.jpg','September 10, 2026')['clues'][0]['time'])

