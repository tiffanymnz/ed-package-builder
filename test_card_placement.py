import copy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PIL import Image
from calculator_evidence import file_digest
from load_identity import VERSION
from load_text_runtime import MODEL_DIGEST
from card_evidence import stage_claim,reviewed_card_mapping
from template_review import assign_template_photo
from loading_sequence import propose_loading_sequence
from photo_flow import PhotoFlowWindow
class CardPlacementTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=str(Path(self.tmp.name)/'evidence.png');Image.new('RGB',(90,70),'red').save(self.p);self.sha=file_digest(self.p)
  self.case=dict(loads=[{'photos':{}},{'photos':{}}],imported_files=[dict(path=self.p)],load_identity_cache={self.p:dict(sha256=self.sha,version=VERSION,model_digest=MODEL_DIGEST,options=[7],status='single_reader',readings=[dict(engine='florence',loads=[7],text='LOAD 7\nHALF FULL')],card_regions=[dict(box=[.2,.2,.4,.5])])},load_card_reviews={self.p:dict(confirmed=True,sha256=self.sha,load=1)})
 def tearDown(self):self.tmp.cleanup()
 def test_literal_card_stage_is_unverified_and_not_a_volume_measurement(self):
  claim=stage_claim(self.case,self.p);self.assertEqual(claim['stage'],'half');self.assertFalse(claim['verified']);self.assertNotIn('volume',claim)
 def test_conflicting_card_stages_do_not_select_a_stage(self):
  self.case['load_identity_cache'][self.p]['readings'].append(dict(engine='standard',loads=[7],text='FULL'));self.assertIsNone(stage_claim(self.case,self.p))
 def test_full_equals_two_cubic_yards_is_not_full_capacity_claim(self):
  self.case['load_identity_cache'][self.p]['readings'][0]['text']='LOAD 7\nFull = 2 CY';self.assertIsNone(stage_claim(self.case,self.p))
 def test_vendor_number_maps_only_after_a_current_review(self):
  self.assertEqual(reviewed_card_mapping(self.case,self.p),1);self.case['load_card_reviews'][self.p]['sha256']='old';self.assertIsNone(reviewed_card_mapping(self.case,self.p))
 def test_package_mapping_conflict_rejects_placement_atomically(self):
  before=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):assign_template_photo(self.case,2,'half',dict(path=self.p,sha256=self.sha))
  self.assertEqual(self.case,before)
 def test_sequence_does_not_guess_a_load_from_visual_similarity(self):
  index=SimpleNamespace(scores={self.p:dict(half=.9)});candidate=dict(path=self.p,sha256=self.sha,basis='Visual Candidate')
  index.shortlist=lambda *args,**kwargs:([candidate],1)
  plan=propose_loading_sequence(self.case,index,1);self.assertTrue(all(v['candidate'] is None for v in plan.values()))
 def test_card_supported_half_is_not_proposed_as_full(self):
  index=SimpleNamespace(scores={self.p:dict(full=.8,half=.1)});candidate=dict(path=self.p,sha256=self.sha,basis='Card Stage Evidence',card_stage='half',group_load_match=True)
  index.shortlist=lambda *args,**kwargs:([candidate],1)
  plan=propose_loading_sequence(self.case,index,1);self.assertIsNotNone(plan['half']['candidate']);self.assertIsNone(plan['full_1']['candidate'])
 def test_new_card_group_filter_shows_only_its_members(self):
  def var(v):return SimpleNamespace(get=lambda:v)
  rows=[dict(path='a',sort_key=(0,),load=None,stage='review',category='container_photos',proposal=dict(group_label='Card Reads Load 7')),dict(path='b',sort_key=(1,),load=None,stage='review',category='container_photos',proposal={})]
  window=SimpleNamespace(rows=rows,category=var('all'),load_filter=var('Card Reads Load 7'),sort=var('Photo Date'),related=None)
  self.assertEqual([r['path'] for r in PhotoFlowWindow.filtered(window)],['a'])
