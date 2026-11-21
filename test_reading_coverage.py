import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from card_reading_views import explicit_hash_load,header_views,text_region_view,retry_has_signal

class ReadingCoverageTests(unittest.TestCase):
 def test_hash_marker_is_not_replaced_by_a_digit(self):
  self.assertEqual(explicit_hash_load('LOAD #3',.98),3)
  for text,score in [('LOAD71',.99),('LOAD #3',.89),('LOAD #0',.99),('LOAD #151',.99),('LOAD #3 X 7',.99),('3',.99)]:self.assertIsNone(explicit_hash_load(text,score))

 def test_retry_views_are_bounded_and_original_pixels_unchanged(self):
  image=Image.new('RGB',(150,300),'#f4dc55');ImageDraw.Draw(image).text((12,30),'LOAD 2',font=ImageFont.load_default(size=30),fill='black');before=image.tobytes()
  views=header_views(image);self.assertLessEqual(len(views),4);self.assertEqual(image.tobytes(),before)
  self.assertTrue(any(n=='rotate-90' for n,im in views));self.assertEqual(header_views(Image.new('RGB',(100,200),'white')),[])

 def test_rectified_text_uses_only_valid_observed_coordinates(self):
  image=Image.new('RGB',(300,200),'white');ImageDraw.Draw(image).text((50,40),'LOAD #2',fill='black');before=image.tobytes()
  self.assertIsNotNone(text_region_view(image,[100,100,600,100,600,400,100,400]))
  self.assertIsNone(text_region_view(image,[-1,0,20,0,20,50,0,50]));self.assertIsNone(text_region_view(image,[0,0]))
  self.assertEqual(image.tobytes(),before)

 def test_blank_or_one_character_crop_does_not_trigger_extra_reads(self):
  self.assertFalse(retry_has_signal(Image.new('RGB',(100,100),'white'),'0'))
  self.assertTrue(retry_has_signal(Image.new('RGB',(100,100),'#f4dc55'),'0'))

 def test_large_card_retries_have_a_bounded_pixel_budget(self):
  image=Image.new('RGB',(2400,4800),'#f4dc55');ImageDraw.Draw(image).rectangle((100,200,1200,600),fill='black')
  views=header_views(image);self.assertTrue(views)
  self.assertTrue(all(max(view.size)<=1600 for name,view in views));self.assertEqual(image.size,(2400,4800))

 def test_conflicting_independent_readers_stay_unresolved(self):
  from load_identity import combine_readings
  result=combine_readings([dict(engine='compact_handwriting',loads=[71]),dict(engine='florence',loads=[1])])
  self.assertEqual(result['status'],'conflict');self.assertIsNone(result['load'])

 def test_broader_classifier_rejects_invalid_vectors(self):
  from photo_category_head import predict_category
  for vector in [np.zeros(512),np.ones(511),np.full(512,np.nan),np.full(512,np.inf)]:
   with self.assertRaises(ValueError):predict_category(vector)

 def test_established_measurement_cue_survives_broader_classifier(self):
  from photo_category_head import predict_category
  with patch('measurement_prior.score',return_value=.9):result=predict_category(np.ones(512))
  self.assertEqual(result['category'],'measurement');self.assertNotIn('load',result)

 def test_unreviewed_same_container_similarity_never_creates_a_trip(self):
  from load_identity import propose_loads
  rows=[dict(path='container-a',sha256='a',category='container_photos',sequence_time='2026-08-24T14:00:00',sequence_source='camera',load=None),dict(path='container-b',sha256='b',category='container_photos',sequence_time='2026-08-24T15:00:00',sequence_source='camera',load=None)]
  case=dict(loads=[dict(photos={}),dict(photos={})],imported_files=[dict(path=r['path']) for r in rows]);before=copy.deepcopy(case)
  self.assertEqual(propose_loads(case,rows),{});self.assertEqual(case,before)

 def test_current_detector_unread_card_is_kept_in_review_queue(self):
  from card_regions import VERSION
  from calculator_evidence import file_digest
  from load_groups import card_candidates
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'card.png';Image.new('RGB',(200,160),'#5588aa').save(path);sha=file_digest(path)
   row=dict(sha256=sha,card_detector_version=VERSION,card_detected=True,card_regions=[dict(box=[.2,.2,.5,.5])])
   case=dict(imported_files=[dict(path=str(path),name=path.name)],local_photo_results={str(path):row})
   self.assertEqual(len(card_candidates(case)),1)
   row['card_detector_version']=-1;self.assertEqual(card_candidates(case),[])

if __name__=='__main__':unittest.main()
