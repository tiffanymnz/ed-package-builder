import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
from small_vision_runtime import download,SmallVisionRuntime,SetupCancelled,allowed_url,prepare_pixels

class Response(io.BytesIO):
 def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}
 def geturl(self):return 'https://huggingface.co/test/file'

class RuntimeTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def asset(self,data):return dict(name='model',size=len(data),sha256=hashlib.sha256(data).hexdigest(),url='https://huggingface.co/test/file')
 def test_download_verifies_and_reuses_bytes(self):
  data=b'small-model';target=self.root/'model';opener=type('Opener',(),{'open':lambda _,*a,**k:Response(data)})()
  download(self.asset(data),target,threading.Event(),lambda *a:None,opener)
  with patch('small_vision_runtime.urllib.request.build_opener') as opened:download(self.asset(data),target,threading.Event(),lambda *a:None)
  opened.assert_not_called();self.assertEqual(target.read_bytes(),data)
 def test_resume_validates_range_and_checksum(self):
  data=b'abcdef';target=self.root/'model';target.with_suffix('.partial').write_bytes(b'abc')
  def opened(request,**kwargs):self.assertEqual(request.get_header('Range'),'bytes=3-');return Response(b'def',206,{'Content-Range':'bytes 3-5/6'})
  download(self.asset(data),target,threading.Event(),lambda *a:None,type('Opener',(),{'open':staticmethod(opened)})())
  self.assertEqual(target.read_bytes(),data)
 def test_bad_checksum_is_not_published(self):
  asset=self.asset(b'good');target=self.root/'model'
  with self.assertRaises(RuntimeError):download(asset,target,threading.Event(),lambda *a:None,type('Opener',(),{'open':lambda _,*a,**k:Response(b'evil')})())
  self.assertFalse(target.exists());self.assertFalse(target.with_suffix('.partial').exists())
 def test_cancel_leaves_no_complete_model(self):
  event=threading.Event();event.set();target=self.root/'model'
  with self.assertRaises(SetupCancelled):download(self.asset(b'a'),target,event,lambda *a:None)
  self.assertFalse(target.exists())
 def test_image_preprocessing_is_cpu_float_tensor(self):
  from PIL import Image
  import numpy as np
  path=self.root/'test.png';Image.new('RGB',(100,200),'white').save(path)
  values=prepare_pixels(path)
  self.assertEqual(values.shape,(1,3,224,224));self.assertEqual(values.dtype,np.float32)
 def test_classifier_requests_only_cpu_provider(self):
  import numpy as np
  from clip_categories import CATEGORY_VECTORS
  from PIL import Image
  runtime=SmallVisionRuntime(self.root);path=self.root/'test.png';Image.new('RGB',(100,100),'white').save(path)
  with patch.object(runtime,'verify'),patch('small_vision_runtime.ort.InferenceSession') as session:
   vector=np.array([CATEGORY_VECTORS['documents']],dtype=np.float32)
   session.return_value.run.return_value=[vector]
   result=runtime.classify(path)
   self.assertEqual(result['category'],'unclear');self.assertFalse(result['verified'])
   self.assertEqual(session.call_args.kwargs['providers'],['CPUExecutionProvider'])
  runtime.stop()
 def test_remove_only_owns_sorting_root(self):
  parent=self.root/'case.json';parent.write_text('original-case')
  runtime=SmallVisionRuntime(self.root/'sorting');runtime.root.mkdir();(runtime.root/'model.gguf').write_bytes(b'weights')
  runtime.remove();self.assertEqual(parent.read_text(),'original-case');self.assertFalse(runtime.root.exists())
 def test_download_hosts_are_limited_to_public_release_hosts(self):
  for url in ['http://huggingface.co/file','https://evil.test/file','https://user:pass@huggingface.co/file']:self.assertFalse(allowed_url(url))
  self.assertTrue(allowed_url('https://release-assets.githubusercontent.com/file'))

if __name__=='__main__':unittest.main()
