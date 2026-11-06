import copy,tempfile,threading,queue,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from calculator_evidence import file_digest
from photo_flow import BackgroundPhotoWork
class InlineThread:
 def __init__(self,target,**kwargs):self.target=target
 def start(self):self.target()
class BackgroundCards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'photo.png');Image.new('RGB',(90,70),'white').save(self.path);self.sha=file_digest(self.path)
  self.case=dict(imported_files=[dict(path=self.path)],local_photo_results={self.path:dict(sha256=self.sha,card_regions=[dict(box=[.1,.1,.5,.5])])},photo_text_cache={})
  self.worker=SimpleNamespace(case=self.case,cancel=threading.Event(),reader_running=False,load_failure=False,priority=[],load_attempted=set(),events=queue.Queue())
 def tearDown(self):self.tmp.cleanup()
 def run_worker(self):
  with patch('photo_flow.threading.Thread',InlineThread),patch('load_identity.card_candidate',return_value=True),patch('load_text_runtime.RUNTIME.ready',return_value=True),patch('load_identity.read_load_card',return_value={'options':[2],'status':'single_reader'}) as reader:
   BackgroundPhotoWork.read_loads(self.worker);return reader.call_count
 def test_visual_card_can_be_read_before_ordinary_ocr_arrives(self):self.assertEqual(self.run_worker(),1)
 def test_reader_does_not_repeat_identical_attempt(self):self.run_worker();self.assertEqual(self.run_worker(),0)
 def test_new_basic_text_is_checked_for_reader_disagreement(self):
  self.run_worker()
  from load_identity import VERSION
  from load_text_runtime import MODEL_DIGEST
  self.case['load_identity_cache']={self.path:dict(sha256=self.sha,version=VERSION,model_digest=MODEL_DIGEST,options=[2],status='single_reader')}
  self.case['photo_text_cache'][self.path]=dict(sha256=self.sha,text='LOAD 3');self.assertEqual(self.run_worker(),1)
 def test_stale_source_is_not_read_or_published(self):
  Image.new('RGB',(90,70),'red').save(self.path);self.assertEqual(self.run_worker(),0);self.assertTrue(self.worker.events.empty())
