"""Native CPU packaging check using synthetic pixels and preverified local weights."""
import json,os,sys,tempfile,time
from pathlib import Path

def run(report_path):
    result=dict(status='FAIL',app_frozen=bool(getattr(sys,'frozen',False)),synthetic_only=True);runtime=None
    try:
        import numpy as np
        from PIL import Image
        from small_vision_runtime import SmallVisionRuntime,ASSETS,digest
        from review_assist import decode_embedding
        model_dir=os.environ.get('ED_PHOTO_TEST_MODEL_DIR')
        if not model_dir:raise ValueError('Set ED_PHOTO_TEST_MODEL_DIR to verified local test weights.')
        runtime=SmallVisionRuntime(model_dir);runtime.verify()
        with tempfile.TemporaryDirectory(prefix='ed_vision_smoke_') as folder:
            path=Path(folder)/'synthetic.png';pixels=np.zeros((240,320,3),dtype=np.uint8)
            pixels[:,:,0]=np.arange(320,dtype=np.uint16)[None,:]%256;pixels[:,:,1]=np.arange(240,dtype=np.uint8)[:,None];pixels[30:170,60:260,2]=220;Image.fromarray(pixels).save(path)
            source_sha=digest(path);start=time.monotonic();prediction=runtime.classify(path);vector=decode_embedding({'prediction':prediction})
            assert vector is not None and vector.shape==(512,) and np.isfinite(vector).all(),'Invalid native embedding'
            assert .99<float(np.linalg.norm(vector))<1.01,'Embedding is not normalized'
            assert digest(path)==source_sha,'Source image changed'
            result.update(status='PASS',provider=runtime.session.get_providers(),embedding_dimensions=len(vector),seconds=time.monotonic()-start,model_sha256=ASSETS[0]['sha256'])
    except Exception as exc:
        import traceback
        result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:
        if runtime:runtime.stop()
    Path(report_path).parent.mkdir(parents=True,exist_ok=True);Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1
