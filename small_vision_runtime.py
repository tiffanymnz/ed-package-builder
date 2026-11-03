"""App-owned CPU image classifier with a verified one-time model download."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageOps
import onnxruntime as ort
ort.disable_telemetry_events()
from clip_categories import CATEGORY_VECTORS, MODEL_REVISION

MODEL_ID='ed-photo-sorter-light'
ASSETS=[dict(name='vision.onnx',size=89117001,sha256='583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299',url='https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/'+MODEL_REVISION+'/onnx/vision_model_quantized.onnx')]
MODEL_DIGEST=hashlib.sha256((ASSETS[0]['sha256']+json.dumps(CATEGORY_VECTORS,sort_keys=True)).encode()).hexdigest()

class SetupCancelled(Exception):pass

def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):result.update(block)
    return result.hexdigest()

def allowed_url(url):
    parsed=urllib.parse.urlsplit(url);host=(parsed.hostname or '').lower()
    return parsed.scheme=='https' and not parsed.username and not parsed.password and (host in {'github.com','huggingface.co','hf.co'} or host.endswith(('.githubusercontent.com','.huggingface.co','.hf.co')))

class DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed_url(newurl):raise RuntimeError('Download redirected to an unapproved source.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(asset,target,cancel,progress,opener=None):
    target=Path(target)
    if target.is_file() and target.stat().st_size==asset['size'] and digest(target)==asset['sha256']:
        progress(asset['size'],asset['size']);return
    if not allowed_url(asset['url']):raise RuntimeError('Unapproved download source.')
    target.parent.mkdir(parents=True,exist_ok=True);partial=target.with_suffix(target.suffix+'.partial')
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>asset['size']:partial.unlink();offset=0
    if offset==asset['size']:
        if digest(partial)==asset['sha256']:os.replace(partial,target);progress(offset,offset);return
        partial.unlink();offset=0
    headers={'User-Agent':'ED-Package-Builder/24'}
    if offset:headers['Range']=f'bytes={offset}-'
    open_request=(opener or urllib.request.build_opener(DownloadRedirect())).open
    if cancel.is_set():raise SetupCancelled()
    with open_request(urllib.request.Request(asset['url'],headers=headers),timeout=45) as response:
        if not allowed_url(response.geturl()):raise RuntimeError('Unapproved download source.')
        status=response.status
        if status==206:
            if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise RuntimeError('Download resume position did not match.')
        elif status==200:offset=0
        else:raise RuntimeError(f'Download failed (HTTP {status}).')
        with partial.open('ab' if offset else 'wb') as output:
            total=offset
            while True:
                if cancel.is_set():raise SetupCancelled()
                block=response.read(min(1024*1024,asset['size']-total+1))
                if not block:break
                total+=len(block)
                if total>asset['size']:raise RuntimeError('Download exceeded its verified size.')
                output.write(block);progress(total,asset['size'])
    if total!=asset['size']:raise RuntimeError('Download was interrupted. Choose Set Up Photo Sorting to resume.')
    if digest(partial)!=asset['sha256']:
        partial.unlink();raise RuntimeError('Download verification failed. Choose setup to retry.')
    os.replace(partial,target)

def prepare_pixels(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB')
        image=ImageOps.fit(image,(224,224),method=Image.Resampling.BICUBIC)
    pixels=np.asarray(image,dtype=np.float32)/255
    pixels=(pixels-np.array([.48145466,.4578275,.40821073],np.float32))/np.array([.26862954,.26130258,.27577711],np.float32)
    return pixels.transpose(2,0,1)[None]

class SmallVisionRuntime:
    def __init__(self,root=None):
        self.root=Path(root) if root else Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'.local'/'share'))/'EDPackageBuilder'/'PhotoSortingLight'
        self.session=None;self.lock=threading.RLock();self.idle_timer=None
        atexit.register(self.stop)

    def ready(self):
        asset=ASSETS[0];path=self.root/asset['name']
        return path.is_file() and path.stat().st_size==asset['size']

    def setup(self,cancel,progress):
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(self.root).free<250_000_000 and not self.ready():raise RuntimeError('Free at least 250 MB for setup. The photo model uses about 90 MB.')
            asset=ASSETS[0]
            download(asset,self.root/asset['name'],cancel,lambda done,total:progress(f'Downloading Photo Model: {done/1e6:.0f} / {total/1e6:.0f} MB',done,total))
            self.verify();progress('Photo sorting is ready. The download is complete.',1,1)

    def verify(self):
        asset=ASSETS[0]
        if not self.ready():raise RuntimeError('Choose Set Up Photo Sorting first.')
        if digest(self.root/asset['name'])!=asset['sha256']:raise RuntimeError('The photo model needs repair. Run setup again.')

    def start(self):
        with self.lock:
            if self.session is not None:return
            self.verify()
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            self.session=ort.InferenceSession(str(self.root/'vision.onnx'),sess_options=options,providers=['CPUExecutionProvider'])

    def classify(self,path):
        with self.lock:
            self.start()
            if self.idle_timer:self.idle_timer.cancel()
            try:
                vector=self.session.run(None,{'pixel_values':prepare_pixels(path)})[0][0]
                vector=vector/max(float(np.linalg.norm(vector)),1e-12)
                scores=sorted(((key,float(np.dot(vector,np.asarray(value,np.float32)))) for key,value in CATEGORY_VECTORS.items()),key=lambda item:item[1],reverse=True)
                best,score=scores[0];margin=score-scores[1][1]
                from photo_category_head import predict_category,image_has_content
                adapted=predict_category(vector)
                if not image_has_content(path):adapted['category']='unclear'
                category=adapted['category']
                from review_assist import encode_embedding
                return dict(embedding=encode_embedding(vector),category=category,category_score=adapted['category_score'],head_version=adapted['head_version'],load_number=None,reason='Visual category suggestion; confirm the photo purpose.',verified=False,
                            similarity=round(score,4),margin=round(margin,4))
            finally:
                self.idle_timer=threading.Timer(300,self.stop);self.idle_timer.daemon=True;self.idle_timer.start()

    def stop(self):
        with self.lock:
            if self.idle_timer:self.idle_timer.cancel();self.idle_timer=None
            self.session=None

    def remove(self):
        with self.lock:
            self.stop()
            if self.root.exists():shutil.rmtree(self.root)

    def storage_bytes(self):
        return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()) if self.root.exists() else 0

RUNTIME=SmallVisionRuntime()
