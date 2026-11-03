import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image,ImageFilter
from review_assist import image_features,repeat_groups,encode_embedding,match_examples,visible_load_numbers,checked_rows,confirm_load_membership
from calculator_evidence import file_digest

class ReviewAssistTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.rows={};self.records=[]
  self.case={'loads':[{'photos':{}},{'photos':{}}],'before_photos':[],'during_photos':[],'after_photos':[]}
  self.pattern=np.random.default_rng(7).integers(0,255,(250,350,3),dtype=np.uint8)
 def tearDown(self):self.temp.cleanup()
 def category_fixture(self):
  from review_assist import confirm_categories
  a=self.photo('property.png',vector=self.vector(1));b=self.photo('document.png',array=np.roll(self.pattern,1,axis=0),category='documents',vector=self.vector(2));c=self.photo('unclear.png',array=np.roll(self.pattern,2,axis=0),category='unclear',vector=self.vector(1))
  confirm_categories(self.case,[a],'property_photos',self.rows);confirm_categories(self.case,[b],'documents',self.rows)
  return a,b,c
 def test_case_examples_supplement_unclear_without_assigning_evidence(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();out=category_matches(self.records,self.rows,self.case)
  self.assertEqual(out[c]['category'],'property_photos');self.assertEqual(out[c]['basis'],'From Your Examples')
  self.assertEqual(self.rows[c]['prediction']['category'],'unclear')
  self.assertEqual(self.case['loads'][0]['photos'],{});self.assertEqual(self.case['before_photos'],[])
 def test_category_examples_need_competing_types_before_propagating(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.case['photo_category_examples'].pop(b)
  self.assertEqual(category_matches(self.records,self.rows,self.case)[c]['category'],'unclear')
 def test_confident_model_disagreement_is_flagged_instead_of_overwritten(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.rows[c]['prediction']['category']='measurement'
  out=category_matches(self.records,self.rows,self.case)[c]
  self.assertEqual(out['category'],'unclear');self.assertEqual(out['basis'],'Category Conflict')
  self.assertEqual(self.rows[c]['prediction']['category'],'measurement')
 def test_equally_similar_category_examples_leave_target_unclear(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.rows[b]['prediction']['embedding']=encode_embedding(self.vector(1))
  self.assertEqual(category_matches(self.records,self.rows,self.case)[c]['category'],'unclear')
 def test_changed_source_rejects_whole_category_batch(self):
  from review_assist import confirm_categories
  a=self.photo('a.png');b=self.photo('b.png');Path(b).write_bytes(b'changed')
  with self.assertRaises(ValueError):confirm_categories(self.case,[a,b],'documents',self.rows)
  self.assertNotIn('photo_category_examples',self.case)
 def test_stale_category_example_is_not_used(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.case['photo_category_examples'][a]['sha256']='stale'
  self.assertEqual(category_matches(self.records,self.rows,self.case)[c]['category'],'unclear')
 def test_reviewed_category_can_correct_the_model_without_new_inference(self):
  from review_assist import confirm_categories,category_matches
  a=self.photo('Before Photo.png',category='property_photos');confirm_categories(self.case,[a],'measurement',self.rows)
  out=category_matches(self.records,self.rows,self.case)[a]
  self.assertEqual(out['category'],'measurement');self.assertEqual(out['basis'],'Reviewed Category')
 def test_examples_do_not_leak_to_other_cases(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.assertEqual(category_matches(self.records,self.rows,{})[c]['category'],'unclear')
 def test_confirmed_property_stages_can_supply_category_examples(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.case['photo_category_examples'].pop(a)
  self.case['property_stage_reviews']={a:dict(stage='after',visual_confirmed=True,sha256=self.rows[a]['sha256'])}
  self.assertEqual(category_matches(self.records,self.rows,self.case)[c]['basis'],'From Your Examples')
 def test_malformed_features_do_not_produce_case_predictions(self):
  from review_assist import category_matches
  a,b,c=self.category_fixture();self.rows[c]['prediction']['embedding']='bad'
  self.assertEqual(category_matches(self.records,self.rows,self.case)[c]['category'],'unclear')
 def test_identical_copies_with_different_labels_are_flagged(self):
  from review_assist import confirm_categories,category_matches
  a=self.photo('a.png',vector=self.vector(1));b=self.photo('b.png',vector=self.vector(1))
  confirm_categories(self.case,[a],'property_photos',self.rows);confirm_categories(self.case,[b],'documents',self.rows)
  out=category_matches(self.records,self.rows,self.case)
  self.assertEqual(out[a]['basis'],'Category Conflict');self.assertEqual(out[b]['basis'],'Category Conflict')
 def test_similar_views_rank_without_assigning_stage_or_load(self):
  from review_assist import similar_views
  a=self.photo('a.png',vector=self.vector(1));b=self.photo('b.png',vector=self.vector(1));c=self.photo('c.png',vector=self.vector(2))
  result=similar_views(a,self.rows)
  self.assertEqual(set(result),{a,b});self.assertNotIn(c,result)
  self.assertFalse(self.case.get('photo_load_assignments'))
  self.assertEqual(self.case['before_photos'],[])
 def test_similar_views_ignore_missing_and_malformed_embeddings(self):
  from review_assist import similar_views
  self.assertEqual(similar_views('missing',self.rows),{})
  a=self.photo('a.png',vector=self.vector(1));self.rows['bad']={'prediction':{'embedding':'bad'}}
  self.assertEqual(set(similar_views(a,self.rows)),{a})
 def photo(self,name,array=None,category='property_photos',vector=None):
  path=self.root/name;Image.fromarray(self.pattern if array is None else array).save(path)
  p=str(path);row={'sha256':file_digest(p),'features':image_features(p),'prediction':{'category':category}}
  if vector is not None:row['prediction']['embedding']=encode_embedding(vector)
  self.rows[p]=row;self.records.append({'path':p,'name':name});return p
 def vector(self,n):
  value=np.zeros(512,np.float32);value[n]=1;return value
 def test_exact_visual_copies_keep_one_without_deleting(self):
  a=self.photo('before_name.png');b=self.photo('totally_different_name.png')
  result=repeat_groups(self.records,self.rows,self.case)
  self.assertEqual(len(result['keep']),1);self.assertEqual(result['index'][a]['count'],2)
  self.assertTrue(Path(a).exists() and Path(b).exists())
 def test_flat_different_colors_are_not_grouped(self):
  self.photo('red.png',np.full((250,350,3),[220,0,0],np.uint8));self.photo('blue.png',np.full((250,350,3),[0,0,220],np.uint8))
  self.assertEqual(len(repeat_groups(self.records,self.rows,self.case)['keep']),2)
 def test_incomplete_cache_does_not_hide_or_crash_review(self):
  p=self.photo('a.png');self.rows[p]['features']={'version':1}
  self.assertEqual(repeat_groups(self.records,self.rows,self.case)['index'],{})
 def test_changed_document_pixels_are_never_near_collapsed(self):
  a=self.photo('invoice.png',category='documents');changed=self.pattern.copy();changed[10:12,10:12]=255
  b=self.photo('invoice_2.png',changed,category='documents')
  self.assertNotEqual(self.rows[a]['features']['pixel_hash'],self.rows[b]['features']['pixel_hash'])
  self.assertEqual(len(repeat_groups(self.records,self.rows,self.case)['keep']),2)
 def test_assigned_evidence_is_always_kept(self):
  a=self.photo('a.png');b=self.photo('b.png');self.case['loads'][0]['photos']['full_1']=a;self.case['loads'][1]['photos']['full_1']=b
  self.assertEqual(repeat_groups(self.records,self.rows,self.case)['keep'],{a,b})
 def test_visible_label_is_used_but_filename_is_not(self):
  p=self.photo('Before_Load_2.png',vector=self.vector(1))
  out=match_examples(self.records,self.rows,self.case);self.assertEqual(out[p]['loads'],[])
  self.case['photo_text_cache']={p:{'sha256':self.rows[p]['sha256'],'text':'LOAD #2'}}
  self.assertEqual(match_examples(self.records,self.rows,self.case)[p]['loads'],[2])
 def test_stale_text_is_ignored(self):
  p=self.photo('p.png');self.case['photo_text_cache']={p:{'sha256':'old','text':'Load 2'}}
  self.assertEqual(match_examples(self.records,self.rows,self.case)[p]['loads'],[])
 def test_reused_container_anchors_are_ambiguous(self):
  a=self.photo('anchor1.png',vector=self.vector(1));b=self.photo('anchor2.png',vector=self.vector(1));target=self.photo('new.png',vector=self.vector(1))
  self.case['loads'][0]['photos']['empty']=a;self.case['loads'][1]['photos']['full_1']=b
  out=match_examples(self.records,self.rows,self.case)[target]
  self.assertEqual(out['loads'],[1,2]);self.assertEqual(out['load_group'],'Multiple Possible Loads')
 def test_each_container_can_have_its_own_load_anchor(self):
  a=self.photo('anchor1.png',vector=self.vector(1));b=self.photo('anchor2.png',vector=self.vector(2));target=self.photo('new.png',vector=self.vector(2))
  self.case['loads'][0]['photos']['empty']=a;self.case['loads'][1]['photos']['empty']=b
  self.assertEqual(match_examples(self.records,self.rows,self.case)[target]['loads'],[2])
 def test_stage_requires_confirmed_example_not_date_or_filename(self):
  a=self.photo('after.png',vector=self.vector(1));b=self.photo('new.png',vector=self.vector(1))
  self.case['before_photos']=[a]
  self.assertIsNone(match_examples(self.records,self.rows,self.case)[b]['stage'])
  self.case['property_stage_reviews']={a:dict(visual_confirmed=True,stage='before',sha256=self.rows[a]['sha256'])}
  self.assertEqual(match_examples(self.records,self.rows,self.case)[b]['stage'],'before')
  self.assertNotIn('property_stage_reviews',self.rows[b])
 def test_documents_never_receive_property_stage_suggestions(self):
  a=self.photo('anchor.png',vector=self.vector(1));b=self.photo('invoice.png',category='documents',vector=self.vector(1))
  self.case['before_photos']=[a];self.case['property_stage_reviews']={a:dict(visual_confirmed=True,stage='before',sha256=self.rows[a]['sha256'])}
  self.assertIsNone(match_examples(self.records,self.rows,self.case)[b]['stage'])
 def test_conflicting_text_and_assignment_are_shown(self):
  a=self.photo('a.png');self.case['loads'][0]['photos']['empty']=a
  self.case['photo_text_cache']={a:{'sha256':self.rows[a]['sha256'],'text':'Load 2'}}
  self.assertEqual(match_examples(self.records,self.rows,self.case)[a]['load_group'],'Conflicting Load Clues')
 def test_load_confirmation_does_not_fill_evidence_slots(self):
  a=self.photo('a.png');confirm_load_membership(self.case,[a],2,self.rows)
  self.assertEqual(self.case['photo_load_assignments'][a]['load'],2)
  self.assertEqual(self.case['loads'][1]['photos'],{})
 def test_load_confirmation_is_atomic_when_a_photo_changes(self):
  a=self.photo('a.png');b=self.photo('b.png');Path(b).write_bytes(b'changed')
  with self.assertRaises(ValueError):confirm_load_membership(self.case,[a,b],1,self.rows)
  self.assertNotIn('photo_load_assignments',self.case)
 def test_existing_evidence_on_another_load_is_protected(self):
  a=self.photo('a.png');self.case['loads'][0]['photos']['empty']=a
  with self.assertRaises(ValueError):confirm_load_membership(self.case,[a],2,self.rows)
 def test_changed_photos_are_removed_from_review_proposals(self):
  a=self.photo('a.png');Path(a).write_bytes(b'changed')
  self.assertEqual(checked_rows(self.records,self.rows),{})
 def test_large_repeat_set_does_not_lose_originals(self):
  a=self.photo('a.png');records=[{'path':f'copy-{i}','name':str(i)} for i in range(1000)];rows={r['path']:self.rows[a] for r in records}
  grouped=repeat_groups(records,rows,self.case)
  self.assertEqual(len(grouped['keep']),1);self.assertEqual(len(grouped['index']),1000)

class MeasurementReadingTests(unittest.TestCase):
 def test_feet_inches_and_fractional_inches(self):
  from cor_package import labeled_measurements
  values=labeled_measurements('Length: 12 ft 6 in\nWidth: 72 inches\nHeight: 4 ft 6 1/2 in')
  self.assertEqual(values['length_ft'],'12.5');self.assertEqual(values['width_ft'],'6')
  self.assertAlmostEqual(float(values['side_height_ft']),4+6.5/12)
 def test_conflicting_invalid_and_unlabeled_values_stay_blank(self):
  from cor_package import labeled_measurements
  for text in ['Length: 12 ft\nLength: 13 ft','Length: 12 ft 14 in','Length: 12 ft 6','12 x 6 x 5','Length: 12 meters']:
   self.assertEqual(labeled_measurements(text),{})

class DocumentReadingTests(unittest.TestCase):
 def test_fresh_bid_ocr_suggests_total_but_requires_confirmation(self):
  from cor_package import apply_document_text_suggestions
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'scan.jpg';path.write_bytes(b'source')
   document=dict(path=str(path),role='other',confirmed=False,amount='')
   case=dict(package_documents=[document],photo_text_cache={str(path):dict(sha256=file_digest(path),text='PRICE QUOTE\nTOTAL $1,250.00')})
   apply_document_text_suggestions(case)
   self.assertEqual(document['role'],'bid');self.assertEqual(document['amount'],'1250.00');self.assertFalse(document['confirmed'])
   document.update(confirmed=True,amount='1200.00');apply_document_text_suggestions(case)
   self.assertEqual(document['amount'],'1200.00')
 def test_stale_ocr_does_not_fill_bid_total(self):
  from cor_package import apply_document_text_suggestions
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'scan.jpg';path.write_bytes(b'new source')
   document=dict(path=str(path),role='bid',confirmed=False,amount='')
   case=dict(package_documents=[document],photo_text_cache={str(path):dict(sha256='old',text='BID\nTOTAL $1,250.00')})
   apply_document_text_suggestions(case);self.assertEqual(document['amount'],'')

if __name__=='__main__':unittest.main()
