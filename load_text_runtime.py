"""Pinned, CPU-only Florence OCR. Model weights stay outside the application."""
import atexit,hashlib,json,os,threading,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from small_vision_runtime import download,digest,SetupCancelled

ASSETS=[{'name': 'config.json', 'size': 5432, 'sha256': 'd90c22ed72eb55291f183fcd9b98ebd3bd3d92bfcffb6c7f6e1606085e793525', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/config.json'}, {'name': 'generation_config.json', 'size': 292, 'sha256': '7b8eb17bbd6cf8a07f619ad83ae03881eff05b6b9237bab89005b40e77783c29', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/generation_config.json'}, {'name': 'preprocessor_config.json', 'size': 2673, 'sha256': 'c892857e34a7082284983a7717717d39c9bf7e574f1f41d80d4c918c97502efa', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/preprocessor_config.json'}, {'name': 'tokenizer.json', 'size': 2297961, 'sha256': 'd69dcdb2323e124ac4f800cb9863ddccea0d7bb11e16125e8df3bd60f2f8aeac', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/tokenizer.json'}, {'name': 'tokenizer_config.json', 'size': 197658, 'sha256': 'd8e64607233cb53b619fb46664f6cad08176c26e0e8735b2d30d888364f19600', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/tokenizer_config.json'}, {'name': 'onnx/decoder_model_merged_quantized.onnx', 'size': 98177697, 'sha256': 'f22f52f980c33df0efa15932c2f3db6d9d3595ce6387eca938b8cfe23dc4c641', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/onnx/decoder_model_merged_quantized.onnx'}, {'name': 'onnx/embed_tokens_quantized.onnx', 'size': 39390433, 'sha256': '6b2258db1c8ee9b160576ccde3cd3814d83a2edaed0dd1c6ca9ff3c38fa62214', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/onnx/embed_tokens_quantized.onnx'}, {'name': 'onnx/encoder_model_quantized.onnx', 'size': 43651493, 'sha256': 'f4ad7a68f1fb875d3bcf735ea14a7021b7ba7e83baf7cf10289881b4ed6d9b85', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/onnx/encoder_model_quantized.onnx'}, {'name': 'onnx/vision_encoder_quantized.onnx', 'size': 93746540, 'sha256': '3b79d54f23f666f731549db23cb070c35a979ce19cbd9720e90e67a78dc9768c', 'url': 'https://huggingface.co/onnx-community/Florence-2-base-ft/resolve/e88a44eaf3791a35eae0c5a47b3dbcd36e67eb6f/onnx/vision_encoder_quantized.onnx'}]
MODEL_DIGEST=hashlib.sha256(''.join(a['sha256'] for a in ASSETS).encode()).hexdigest()

class LoadTextRuntime:
 def __init__(self,root=None):
  self.root=Path(root) if root else Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local'/'share')/'EDPackageBuilder'/'LoadTextReader'
  self.sessions={};self.tokenizer=None;self.lock=threading.RLock();self.idle=None;atexit.register(self.stop)
 def ready(self):return all((self.root/a['name']).is_file() and (self.root/a['name']).stat().st_size==a['size'] for a in ASSETS)
 def setup(self,cancel,progress):
  import shutil
  with self.lock:
   self.root.mkdir(parents=True,exist_ok=True)
   if not self.ready() and shutil.disk_usage(self.root).free<500_000_000:raise RuntimeError('Free 500 MB to set up load-card reading.')
   total=sum(a['size'] for a in ASSETS);completed=0
   for a in ASSETS:
    download(a,self.root/a['name'],cancel,lambda done,size:progress('Preparing Load-Card Reader',completed+done,total));completed+=a['size']
 def start(self):
  if self.sessions:return
  import onnxruntime as ort
  from tokenizers import Tokenizer
  if not self.ready():raise RuntimeError('Load-card reader setup is incomplete.')
  for a in ASSETS:
   if digest(self.root/a['name'])!=a['sha256']:raise RuntimeError('Load-card reader files need repair.')
  options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
  self.sessions={name:ort.InferenceSession(str(self.root/'onnx'/file),sess_options=options,providers=['CPUExecutionProvider']) for name,file in [('vision','vision_encoder_quantized.onnx'),('embed','embed_tokens_quantized.onnx'),('encoder','encoder_model_quantized.onnx'),('decoder','decoder_model_merged_quantized.onnx')]}
  self.tokenizer=Tokenizer.from_file(str(self.root/'tokenizer.json'))
 def read(self,image,task='regions',cancel=None,max_tokens=224):
  with self.lock:
   self.start()
   if self.idle:self.idle.cancel()
   try:return self._read(image,task,cancel or threading.Event(),max_tokens)
   finally:
    self.idle=threading.Timer(300,self.stop);self.idle.daemon=True;self.idle.start()
 def _read(self,image,task,cancel,max_tokens):
  began=time.monotonic()
  if isinstance(image,Image.Image):im=ImageOps.exif_transpose(image).convert('RGB')
  else:
   with Image.open(image) as source:im=ImageOps.exif_transpose(source).convert('RGB')
  pixels=np.asarray(im.resize((768,768),Image.Resampling.BICUBIC),np.float32)/255
  pixels=(pixels-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32);pixels=pixels.transpose(2,0,1)[None]
  if cancel.is_set():raise SetupCancelled()
  vision=self.sessions['vision'].run(None,{'pixel_values':pixels})[0]
  prompt='What is the text in the image, with regions?' if task=='regions' else 'What is the text in the image?'
  ids=np.array([self.tokenizer.encode(prompt).ids],np.int64);embed=self.sessions['embed'].run(None,{'input_ids':ids})[0]
  inputs=np.concatenate([vision,embed],axis=1);mask=np.ones(inputs.shape[:2],np.int64);encoded=self.sessions['encoder'].run(None,{'attention_mask':mask,'inputs_embeds':inputs})[0]
  decoder=self.sessions['decoder'];past={x.name:np.zeros((1,12,0,64),np.float32) for x in decoder.get_inputs() if x.name.startswith('past_key_values')};names=[x.name for x in decoder.get_outputs()];token=2;generated=[]
  for step in range(max_tokens):
   if cancel.is_set():raise SetupCancelled()
   if time.monotonic()-began>45:raise RuntimeError('Load-card reading exceeded its time limit.')
   embed=self.sessions['embed'].run(None,{'input_ids':np.array([[token]],np.int64)})[0]
   values=decoder.run(None,dict(past,inputs_embeds=embed,encoder_attention_mask=mask,encoder_hidden_states=encoded,use_cache_branch=np.array([step>0],np.bool_)))
   token=0 if step==0 else int(values[0][0,-1].argmax());generated.append(token)
   for name,value in zip(names[1:],values[1:]):
    if value.size:past[name.replace('present.','past_key_values.')]=value
   if token==2:break
  return dict(text=self.tokenizer.decode(generated,skip_special_tokens=task!='regions'),truncated=len(generated)==max_tokens)
 def stop(self):
  with self.lock:
   if self.idle:self.idle.cancel();self.idle=None
   self.sessions={};self.tokenizer=None

RUNTIME=LoadTextRuntime()
