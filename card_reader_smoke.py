"""Exercise the actual OCR runtime using synthetic pixels and externally verified CI weights."""
import json,os,sys,tempfile,threading,traceback
from pathlib import Path

def run(report_path):
    result=dict(status='FAIL',app_frozen=bool(getattr(sys,'frozen',False)),synthetic_only=True);reader=None
    try:
        from PIL import Image,ImageDraw,ImageFont
        from load_text_runtime import LoadTextRuntime
        from load_identity import read_load_card
        from calculator_evidence import file_digest
        directory=os.environ.get('ED_CARD_TEST_MODEL_DIR')
        if not directory:raise RuntimeError('Provide the verified CI card-reader model directory.')
        reader=LoadTextRuntime(Path(directory))
        if not reader.ready():raise RuntimeError('Card-reader test assets are missing.')
        with tempfile.TemporaryDirectory(prefix='ed-card-engine-smoke-') as temp:
            path=Path(temp)/'synthetic-card.png';image=Image.new('RGB',(640,480),'white');draw=ImageDraw.Draw(image)
            draw.text((70,90),'LOAD 2',font=ImageFont.load_default(size=56),fill='black');draw.text((70,200),'FULL',font=ImageFont.load_default(size=48),fill='black');image.save(path)
            before=file_digest(path);clue=read_load_card(path,'',threading.Event(),reader)
            assert clue['options']==[2],f"Clean synthetic card was not read: {clue['options']}"
            assert file_digest(path)==before,'Source pixels changed'
            result.update(status='PASS',load_options=clue['options'],reader_version=clue['version'],
                          onnx_cpu_inference=True,source_unchanged=True)
    except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:
        if reader is not None:reader.stop()
    Path(report_path).parent.mkdir(parents=True,exist_ok=True);Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1
