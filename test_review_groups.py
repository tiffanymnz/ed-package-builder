import copy,unittest
import test_evidence_groups as existing
from evidence_groups import propose_evidence_groups,propose_date_review_groups
from PIL import Image
from photo_locations import printed_locations,photo_locations

class ReviewGroupTests(unittest.TestCase):
 setUp=existing.EvidenceGroupTests.setUp
 tearDown=existing.EvidenceGroupTests.tearDown
 card=existing.EvidenceGroupTests.card
 map=existing.EvidenceGroupTests.map
 def date_only(self):
  for row in self.rows:row.update(sequence_date='2026-10-05',sequence_time=None,sequence_source=None)
 def test_date_group_never_enters_template_group_provider(self):
  self.date_only();self.map(0,1);before=copy.deepcopy(self.case)
  hard=propose_evidence_groups(self.case,self.rows);soft=propose_date_review_groups(self.case,self.rows,hard);path=self.rows[2]['path']
  self.assertNotIn(path,hard);self.assertTrue(soft[path]['review_only']);self.assertEqual(soft[path]['load'],1);self.assertEqual(before,self.case)
 def test_two_card_numbers_same_day_withhold_calendar_bucket(self):
  self.date_only();self.card(4,8);self.assertEqual(propose_date_review_groups(self.case,self.rows),{})
 def test_reused_number_dates_withhold_calendar_bucket(self):
  self.date_only();self.rows[4]['sequence_date']='2026-10-06';self.assertEqual(propose_date_review_groups(self.case,self.rows),{})
 def test_unknown_date_is_not_borrowed_from_neighbors(self):
  self.date_only();self.rows[2]['sequence_date']=None;self.assertNotIn(self.rows[2]['path'],propose_date_review_groups(self.case,self.rows))
 def test_changed_photo_is_not_suggested(self):
  self.date_only();Image.new('RGB',(80,60),'white').save(self.rows[2]['path']);self.assertNotIn(self.rows[2]['path'],propose_date_review_groups(self.case,self.rows))
 def test_document_and_property_photos_are_not_bucketed(self):
  self.date_only();self.rows[2]['category']='documents';self.rows[3]['stage']='during';out=propose_date_review_groups(self.case,self.rows);self.assertNotIn(self.rows[2]['path'],out);self.assertNotIn(self.rows[3]['path'],out)
 def test_conflicting_location_prevents_global_card_mapping(self):
  self.map(0,1);self.rows[0]['location_clues']=[dict(key='1 oak st')];self.rows[4]['location_clues']=[dict(key='9 pine rd')]
  out=propose_evidence_groups(self.case,self.rows);self.assertIsNone(out[self.rows[4]['path']]['load']);self.assertNotIn(self.rows[2]['path'],out);self.assertIn('Location Text Differs',out[self.rows[0]['path']]['reason'])
 def test_different_location_not_added_to_calendar_bucket(self):
  self.date_only();self.rows[0]['location_clues']=[dict(key='1 oak st')];self.rows[2]['location_clues']=[dict(key='9 pine rd')]
  self.assertNotIn(self.rows[2]['path'],propose_date_review_groups(self.case,self.rows))
 def test_group_membership_stable_after_reordering(self):
  self.date_only();expected=propose_date_review_groups(self.case,self.rows);self.assertEqual(expected,propose_date_review_groups(self.case,list(reversed(self.rows))))
 def test_dismissed_card_cannot_supply_a_load_clue(self):
  from load_identity import current_clue
  row=self.rows[0];self.case['load_card_dismissals']={row['path']:dict(sha256=row['sha256'])}
  self.assertIsNone(current_clue(self.case,row['path'],row['sha256']))
  self.assertNotIn(row['path'],propose_evidence_groups(self.case,self.rows))
 def test_reconfirming_current_photo_restores_it_after_dismissal(self):
  from load_groups import confirm_card
  row=self.rows[0];self.case['local_photo_results']={row['path']:dict(sha256=row['sha256'])};self.case['load_card_dismissals']={row['path']:dict(sha256=row['sha256'])}
  confirm_card(self.case,row['path'],1,expected_sha=row['sha256'],vendor_number=7)
  self.assertNotIn(row['path'],self.case['load_card_dismissals']);self.assertEqual(propose_evidence_groups(self.case,self.rows)[row['path']]['load'],1)
 def test_source_specific_review_survives_a_reused_number(self):
  self.date_only();self.map(0,1);self.map(4,2);self.rows[4]['sequence_date']='2026-10-06'
  out=propose_evidence_groups(self.case,self.rows)
  self.assertEqual(out[self.rows[0]['path']]['load'],1);self.assertEqual(out[self.rows[4]['path']]['load'],2)
  self.assertNotIn(self.rows[2]['path'],out)
 def test_disagreeing_source_specific_reviews_require_reconciliation(self):
  self.map(0,1);self.rows[0]['load']=2
  out=propose_evidence_groups(self.case,self.rows)
  self.assertIsNone(out[self.rows[0]['path']]['load']);self.assertEqual(out[self.rows[0]['path']]['status'],'card_mapping_conflict')
 def test_hidden_card_can_be_found_for_restoration(self):
  from load_groups import card_candidates
  row=self.rows[0];self.case['local_photo_results']={r['path']:dict(sha256=r['sha256']) for r in self.rows};self.case['load_card_dismissals']={row['path']:dict(sha256=row['sha256'])}
  self.assertNotIn(row['path'],{r['path'] for r in card_candidates(self.case)})
  hidden=next(r for r in card_candidates(self.case,include_hidden=True) if r['path']==row['path']);self.assertTrue(hidden['hidden'])

class LocationTests(unittest.TestCase):
 def test_normalizes_known_street_spelling_without_changing_house_number(self):
  self.assertEqual(printed_locations('120 Example Drive')[0]['key'],printed_locations('120 Example Dr')[0]['key'])
  self.assertNotEqual(printed_locations('120 Example Dr')[0]['key'],printed_locations('122 Example Dr')[0]['key'])
 def test_does_not_mine_dimensions_or_invoice_prose(self):
  self.assertEqual(printed_locations('8 x 5 x 5.5\nLoad 2\n27 cubic yards\nInvoice total $350'),[])
 def test_changed_cache_does_not_supply_location(self):
  c=dict(photo_text_cache={'photo':dict(sha256='old',text='120 Example Dr')});self.assertEqual(photo_locations(c,'photo','new'),[])
