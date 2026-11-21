import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from ed_builder import volume
from cor_package import totals,comparable_bid_amount,bid_fingerprint,financial_fingerprint
from calculator_evidence import measurement_signature,file_digest
import test_evidence_groups as group_tests
from reviewed_stage_examples import suggest_stages
from visual_photo_review import apply_visual_stage

class CalculationTests(unittest.TestCase):
 def case(self,method='full_precision'):
  return dict(loads=[dict(length_ft=8,width_ft=5,side_height_ft=5.5,fill_fraction=fill,quantity_rounding=method) for fill in [1,1,1,.5]],rate_per_cyd=35)
 def test_corrected_package_rounding_is_explicit(self):
  self.assertEqual(str(totals(self.case())['quantity']),'28.52')
  value=totals(self.case('capacity_then_fill'))
  self.assertEqual(str(value['quantity']),'28.53');self.assertEqual(str(value['request']),'648.55')
 def test_method_invalidates_all_confirmations(self):
  a=self.case();b=self.case('capacity_then_fill')
  for fn in [bid_fingerprint,financial_fingerprint]:self.assertNotEqual(fn(a),fn(b))
  self.assertNotEqual(measurement_signature(a['loads'][0]),measurement_signature(b['loads'][0]))
 def test_unknown_rounding_rejected(self):
  with self.assertRaises(ValueError):volume(self.case('unknown')['loads'][0])
 def test_unit_rate_bid_handles_changed_quantity(self):
  bid=dict(amount=945,debris_quantity_cyd=27,unit_rate_per_cyd=35,pricing_basis='per_cyd')
  self.assertEqual(str(comparable_bid_amount(bid,'28.53')),'998.55')
 def test_fixed_bid_does_not_silently_become_unit_rate(self):
  with self.assertRaises(ValueError):comparable_bid_amount(dict(amount=945,debris_quantity_cyd=27),'28.53')
  self.assertEqual(comparable_bid_amount(dict(amount=945,debris_quantity_cyd=27),27),945)
 def test_inconsistent_unit_rate_rejected(self):
  with self.assertRaises(ValueError):comparable_bid_amount(dict(amount=945,debris_quantity_cyd=27,unit_rate_per_cyd=40,pricing_basis='per_cyd'),28)

class ReusedNumberTests(unittest.TestCase):
 setUp=group_tests.EvidenceGroupTests.setUp
 tearDown=group_tests.EvidenceGroupTests.tearDown
 card=group_tests.EvidenceGroupTests.card
 map=group_tests.EvidenceGroupTests.map
 def test_different_dates_withhold_mapping_and_time_propagation(self):
  self.map(0,1);self.rows[4]['sequence_time']='2026-10-06T10:20:00'
  from evidence_groups import propose_evidence_groups
  out=propose_evidence_groups(self.case,self.rows)
  self.assertIsNone(out[self.rows[4]['path']]['load']);self.assertNotIn(self.rows[2]['path'],out)
  self.assertIn('Different Dates',out[self.rows[0]['path']]['reason'])

class StageExampleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.case={};self.rows=[]
  for i in range(5):
   p=Path(self.tmp.name)/f'{i}.png';Image.new('RGB',(20,20),(i*40,30,60)).save(p)
   vec=np.zeros(512,np.float32);vec[i if i<3 else 1]=1
   self.rows.append(dict(path=str(p),sha256=file_digest(p),embedding=vec,category='property_photos'))
  for i,stage in enumerate(['before','during','after']):apply_visual_stage(self.case,[self.rows[i]['path']],stage,True)
 def tearDown(self):self.tmp.cleanup()
 def test_during_suggestion_from_human_examples_never_assigns(self):
  before=copy.deepcopy(self.case);out=suggest_stages(self.case,self.rows)
  self.assertEqual(out[self.rows[3]['path']]['stage'],'during');self.assertFalse(out[self.rows[3]['path']]['verified']);self.assertEqual(before,self.case)
 def test_changed_example_no_longer_teaches(self):
  Image.new('RGB',(20,20),'white').save(self.rows[1]['path']);self.assertNotIn(self.rows[3]['path'],suggest_stages(self.case,self.rows))
 def test_near_tie_remains_unresolved(self):
  self.rows[3]['embedding']=(self.rows[0]['embedding']+self.rows[1]['embedding'])/np.sqrt(2)
  self.assertNotIn(self.rows[3]['path'],suggest_stages(self.case,self.rows))
 def test_documents_never_receive_property_suggestion(self):
  self.rows[3]['category']='documents';self.assertNotIn(self.rows[3]['path'],suggest_stages(self.case,self.rows))
 def test_conflicting_identical_photos_do_not_teach(self):
  source=Path(self.rows[1]['path']);target=Path(self.rows[4]['path']);target.write_bytes(source.read_bytes())
  apply_visual_stage(self.case,[str(target)],'after',True)
  self.assertNotIn(self.rows[3]['path'],suggest_stages(self.case,self.rows))

class ReviewedCardStageTests(unittest.TestCase):
 def test_reviewed_fraction_is_source_bound_and_preserves_reader(self):
  from unittest.mock import patch
  from load_groups import confirm_card
  from card_evidence import stage_claim
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'fraction.png';Image.new('RGB',(100,80),'white').save(p);sha=file_digest(p)
   case=dict(loads=[{}],imported_files=[dict(path=str(p))],local_photo_results={str(p):dict(sha256=sha)},load_identity_cache={str(p):dict(text='12')})
   original=copy.deepcopy(case['load_identity_cache']);confirm_card(case,str(p),1,sha,2,stage='half')
   with patch('card_regions.locate_cards',return_value=[dict(box=[.1,.1,.3,.3])]):
    self.assertEqual(stage_claim(case,str(p))['stage'],'half')
   self.assertEqual(case['load_identity_cache'],original)
   Image.new('RGB',(100,80),'black').save(p);self.assertIsNone(stage_claim(case,str(p)))
 def test_invalid_stage_is_rejected_before_mutation(self):
  from load_groups import confirm_card
  case={}
  with self.assertRaises(ValueError):confirm_card(case,'missing',1,stage='12')
  self.assertEqual(case,{})
