import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from local_photo_sorter import batch,installed_models,parse_prediction,suggested_category,read_cache,VERSION,MODEL_ID,MODEL_DIGEST

class LocalSorterTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.model={'name':MODEL_ID,'digest':MODEL_DIGEST}
  self.records=[]
  for i,color in enumerate(['blue','red','green']):
   path=self.folder/f'photo{i}.png';Image.new('RGB',(80,80),color).save(path);self.records.append(dict(path=str(path),name=path.name))
  self.cache=self.folder/'cache.json'
 def tearDown(self):self.temp.cleanup()
 def test_resume_moves_past_cached_first_batch(self):
  calls=[];infer=lambda path,model:(calls.append(path) or parse_prediction({'category':'property_after'}))
  first=batch(self.records,self.model,self.cache,threading.Event(),lambda *a:None,limit=1,infer=infer)
  second=batch(self.records,self.model,self.cache,threading.Event(),lambda *a:None,limit=1,infer=infer)
  self.assertEqual(len(calls),2);self.assertNotEqual(calls[0],calls[1]);self.assertEqual(second['reused'],1)
  self.assertEqual(len(read_cache(self.cache)),2)
 def test_identical_image_uses_one_inference_and_preserves_original(self):
  self.records[1]['path']=str(self.folder/'copy.png');Path(self.records[1]['path']).write_bytes(Path(self.records[0]['path']).read_bytes())
  calls=[]
  batch(self.records[:2],self.model,self.cache,threading.Event(),lambda *a:None,infer=lambda p,m:(calls.append(p) or parse_prediction({'category':'invoice'})))
  self.assertEqual(len(calls),1);self.assertEqual(len(read_cache(self.cache)),2)
 def test_cancel_and_failure_preserve_completed_results(self):
  event=threading.Event()
  batch(self.records,self.model,self.cache,event,lambda *a:event.set(),infer=lambda p,m:parse_prediction({'category':'measurement'}))
  self.assertEqual(len(read_cache(self.cache)),1)
  def fail(*a):raise RuntimeError('offline')
  with self.assertRaises(RuntimeError):batch(self.records,self.model,self.cache,threading.Event(),lambda *a:None,infer=fail)
  self.assertEqual(len(read_cache(self.cache)),1)
 def test_changed_contents_invalidate_suggestion(self):
  batch(self.records[:1],self.model,self.cache,threading.Event(),lambda *a:None,infer=lambda p,m:parse_prediction({'category':'invoice'}))
  case={'local_photo_results':read_cache(self.cache)};path=self.records[0]['path']
  self.assertEqual(suggested_category(case,path),'Invoices')
  Image.new('RGB',(80,80),'black').save(path)
  self.assertEqual(suggested_category(case,path),'Not Analyzed')
 def test_model_is_offered_only_after_automatic_setup(self):
  from small_vision_runtime import MODEL_ID,MODEL_DIGEST
  with patch('local_photo_sorter.RUNTIME.ready',return_value=False):self.assertEqual(installed_models(),[])
  with patch('local_photo_sorter.RUNTIME.ready',return_value=True):self.assertEqual(installed_models(),[dict(name=MODEL_ID,digest=MODEL_DIGEST)])
 def test_changed_photo_gets_new_repeat_features(self):
  infer=lambda p,m:parse_prediction({'category':'property_photos'})
  batch(self.records[:1],self.model,self.cache,threading.Event(),lambda *a:None,infer=infer)
  path=self.records[0]['path'];old=read_cache(self.cache)[path]['features']['pixel_hash']
  Image.new('RGB',(80,80),'black').save(path)
  batch(self.records[:1],self.model,self.cache,threading.Event(),lambda *a:None,infer=infer)
  self.assertNotEqual(read_cache(self.cache)[path]['features']['pixel_hash'],old)
 def test_cached_visual_features_upgrade_without_model_inference(self):
  import numpy as np
  from review_assist import encode_embedding
  from calculator_evidence import file_digest
  from local_photo_sorter import save_cache
  path=self.records[0]['path']
  save_cache(self.cache,{path:dict(sha256=file_digest(path),model_digest=MODEL_DIGEST,prompt_version='old-head',prediction={'embedding':encode_embedding(np.ones(512)),'category':'documents'})})
  with patch('photo_category_head.predict_category',return_value={'category':'measurement','category_score':.9,'head_version':'category-head-1'}),patch('photo_category_head.image_has_content',return_value=True),patch('local_photo_sorter.analyze',side_effect=AssertionError('Must not run model')) as infer:
   batch(self.records[:1],self.model,self.cache,threading.Event(),lambda *a:None,infer=infer)
   infer.assert_not_called()
  result=read_cache(self.cache)[path]
  self.assertEqual(result['prompt_version'],VERSION);self.assertEqual(result['prediction']['category'],'measurement')
 def test_blank_cached_photo_is_not_upgraded_to_document(self):
  import numpy as np
  from review_assist import encode_embedding
  from calculator_evidence import file_digest
  from local_photo_sorter import save_cache
  path=self.records[0]['path']
  save_cache(self.cache,{path:dict(sha256=file_digest(path),model_digest=MODEL_DIGEST,prompt_version='old-head',prediction={'embedding':encode_embedding(np.ones(512))})})
  with patch('photo_category_head.predict_category',return_value={'category':'documents','category_score':.99,'head_version':'category-head-1'}):
   batch(self.records[:1],self.model,self.cache,threading.Event(),lambda *a:None,infer=lambda *a:None)
  self.assertEqual(read_cache(self.cache)[path]['prediction']['category'],'unclear')
 def test_invalid_model_category_stays_unclear_without_load_guess(self):
  result=parse_prediction({'category':'made-up','load_number':'3','verified':True})
  self.assertEqual(result['category'],'unclear');self.assertIsNone(result['load_number']);self.assertFalse(result['verified'])

if __name__=='__main__':unittest.main()
