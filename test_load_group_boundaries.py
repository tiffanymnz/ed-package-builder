"""Reviewable groups must respect reset, receipt and manual-review boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from calculator_evidence import file_digest
from load_groups import propose_groups, card_candidates
from photo_semantics import likely_receipt
from review_assist import encode_embedding

class LoadGroupBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.paths=[]
        self.case=dict(loads=[{'photos':{}},{'photos':{}}],imported_files=[],local_photo_results={})
        for i in range(9):
            path=str(Path(self.temp.name)/f'{i}.png');Image.new('RGB',(100,80),(i*20,80,90)).save(path);self.paths.append(path)
            vector=np.zeros(512);vector[i]=1
            self.case['imported_files'].append(dict(path=path))
            self.case['local_photo_results'][path]=dict(sha256=file_digest(path),prediction={'embedding':encode_embedding(vector)})
        self.receipt_indices={3,8};self.empty_indices={0,5}
        self.cards=[dict(path=self.paths[i],position=i,reviewed_load=n,sha256=file_digest(self.paths[i])) for i,n in [(1,1),(6,2)]]
    def tearDown(self):self.temp.cleanup()
    def rows(self):return [dict(path=p,sha256=file_digest(p),load=None,stage='review',category='container_photos') for p in self.paths]
    def signals(self,row):
        index=int(np.argmax(__import__('review_assist').decode_embedding(row)))
        return dict(load_board=.15,loaded_container=.32,empty_container=.29,container_measurement=.28,property=.20,grass_measurement=.17,bin_interior=.18,pointing_hand=.18,receipt=.2,irrelevant_measurement=.18,disposal_scene=.4 if index==4 else .2,loading_scene=.3)
    def purpose(self,vector):
        index=int(np.argmax(vector));result=dict(empty=.01,full=.7,quarter=.02,half=.02,three_quarters=.02,other=.05,height=.01,width=.01,length=.01,receipt=.01)
        if index in self.empty_indices:result.update(empty=.65,full=.05)
        if index in self.receipt_indices:result.update(receipt=.8,full=.01)
        return result
    def groups(self,rows=None):
        with patch('load_groups.card_candidates',return_value=self.cards),patch('load_groups.scores',side_effect=self.signals),patch('template_slot_head.predict_slots',side_effect=self.purpose),patch('load_groups.likely_receipt',side_effect=lambda values,path,purpose=None:self.paths.index(path) in self.receipt_indices):
            return propose_groups(self.case,rows or self.rows())
    def test_import_order_and_empty_resets_do_not_supply_load_identity(self):
        before=copy.deepcopy(self.case);self.assertEqual(self.groups(),{});self.assertEqual(self.case,before)
    def test_unconfirmed_card_cannot_group_neighbours_by_position(self):
        self.cards[1]['reviewed_load']=None;self.assertEqual(self.groups(),{})
    def test_missing_next_card_does_not_allow_crossing_an_empty_reset(self):
        self.cards=self.cards[:1];self.assertEqual(self.groups(),{})
    def test_receipts_and_disposal_need_identity_not_adjacent_file_order(self):
        self.empty_indices={0};self.receipt_indices={3,5,8};self.assertEqual(self.groups(),{})
    def test_manual_category_load_and_property_stage_are_protected(self):
        rows=self.rows();rows[2]['load']=2;rows[4]['stage']='during'
        self.case['photo_category_examples']={self.paths[7]:dict(sha256=file_digest(self.paths[7]),category='property_photos')}
        groups=self.groups(rows)
        for i in (2,4,7):self.assertNotIn(self.paths[i],groups)
    def test_duplicate_card_bytes_do_not_establish_two_trips(self):
        self.cards[1]['sha256']=self.cards[0]['sha256'];self.assertEqual(self.groups(),{})
    def test_unconfirmed_review_record_cannot_supply_a_load_number(self):
        path=self.paths[1];self.case['load_card_reviews']={path:dict(sha256=file_digest(path),load=2,confirmed=False)}
        with patch('load_groups.scores',return_value={}):cards=card_candidates(self.case)
        self.assertEqual(len(cards),1);self.assertIsNone(cards[0]['reviewed_load'])
    def test_property_like_paper_is_not_a_receipt_when_purpose_head_disagrees(self):
        values=dict(receipt=.4,property=.2,loaded_container=.2,load_board=.2)
        with patch('photo_semantics.paper_fraction',return_value=.3):
            self.assertFalse(likely_receipt(values,self.paths[0],dict(receipt=.04,other=.6)))
            self.assertTrue(likely_receipt(values,self.paths[0],dict(receipt=.6,other=.04)))

    def test_conflicting_exact_clocks_do_not_create_identity(self):
        rows=self.rows()
        for i in (0,2,3):rows[i].update(sequence_source='camera',sequence_time='2026-11-05T10:'+{0:'00',2:'20',3:'10'}[i])
        self.assertEqual(self.groups(rows),{})
    def test_date_only_never_creates_a_numbered_group(self):
        rows=self.rows();rows[0]['sequence_time']='2026-11-05';rows[2]['sequence_time']='2026-11-04';self.assertEqual(self.groups(rows),{})

if __name__=='__main__':unittest.main()
