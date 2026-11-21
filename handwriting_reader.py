"""Optional compact annotation reader, using the existing ONNX runtime.

Weights are bundled with the application; this module does not download files.
Official model: PaddlePaddle/en_PP-OCRv5_mobile_rec (Apache-2.0).
"""
import atexit,threading,hashlib,sys
from pathlib import Path
import numpy as np
from PIL import Image
MODEL_SIZE=7850705
MODEL_SHA256='a3a00067ddacc6e785d3282f0c858ddd284591d2d79bc5aa6cd514e8f6e491bc'
CHARACTERS=['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '_', '`', '{', '|', '}', '^', '~', '©', '®', '℉', '№', 'Ω', '℮', '™', '∆', '✓', '✔', '✗', '✘', '✕', '☑', '☒', '●', '▪', '▫', '◼', '▶', '◀', '⬆', '¤', '¦', '§', '¨', 'ª', '«', '¬', '¯', '°', '²', '³', '´', 'µ', '¶', '¸', '¹', 'º', '»', '¼', '½', '¾', '¿', '×', '‐', '‑', '‒', '—', '―', '‖', '‗', '‘', '’', '‚', '‛', '“', '”', '„', '‟', '†', '‡', '‣', '․', '…', '‧', '‰', '‴', '‵', '‶', '‷', '‸', '‹', '›', '※', '‼', '‽', '‾', '−', '₤', '₡', '₹', '₽', '₴', '₿', '¢', '€', '£', '¥', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ', 'Ⅹ', 'Ⅺ', 'Ⅻ', 'ⅰ', 'ⅱ', 'ⅲ', 'ⅳ', 'ⅴ', 'ⅵ', 'ⅶ', 'ⅷ', 'ⅸ', 'ⅹ', 'ⅺ', 'ⅻ', '➀', '➁', '➂', '➃', '➄', '➅', '➆', '➇', '➈', '➉', '➊', '➋', '➌', '➍', '➎', '➏', '➐', '➑', '➒', '➓', '❶', '❷', '❸', '❹', '❺', '❻', '❼', '❽', '❾', '❿', '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '↑', '→', '↓', '↕', '←', '↔', '⇒', '⇐', '⇔', '∀', '∃', '∄', '∴', '∵', '∝', '∞', '∩', '∪', '∂', '∫', '∬', '∭', '∮', '∯', '∰', '∑', '∏', '√', '∛', '∜', '∱', '∲', '∳', '∶', '∷', '∼', '∖', '∗', '≈', '≠', '≡', '≤', '≥', '⊂', '⊃', '⊥', '⊾', '⊿', '□', '∥', '∋', 'ƒ', '′', '″', 'À', 'Á', 'Â', 'Ã', 'Ä', 'Å', 'Æ', 'Ç', 'È', 'É', 'Ê', 'Ë', 'Ì', 'Í', 'Î', 'Ï', 'Ð', 'Ñ', 'Ò', 'Ó', 'Ô', 'Õ', 'Ö', 'Ø', 'Ù', 'Ú', 'Û', 'Ü', 'Ý', 'Þ', 'à', 'á', 'â', 'ã', 'ä', 'å', 'æ', 'ç', 'è', 'é', 'ê', 'ë', 'ì', 'í', 'î', 'ï', 'ð', 'ñ', 'ò', 'ó', 'ô', 'õ', 'ö', 'ø', 'ù', 'ú', 'û', 'ü', 'ý', 'þ', 'ÿ', 'Α', 'Β', 'Γ', 'Δ', 'Ε', 'Ζ', 'Η', 'Θ', 'Ι', 'Κ', 'Λ', 'Μ', 'Ν', 'Ξ', 'Ο', 'Π', 'Ρ', 'Σ', 'Τ', 'Υ', 'Φ', 'Χ', 'Ψ', 'Ω', 'α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', 'θ', 'ι', 'κ', 'λ', 'μ', 'ν', 'ξ', 'ο', 'π', 'ρ', 'σ', 'ς', 'τ', 'υ', 'φ', 'χ', 'ψ', 'ω', 'Å', 'ℏ', '⌀', '⍺', '⍵', '𝑢', '𝜓', '०', '‥', '︽', '﹥', '•', '÷', '∕', '∙', '⋅', '·', '±', '∓', '∟', '∠', '∡', '∢', '℧', '☺']

class HandwritingReader:
 def __init__(self,root):self.path=Path(root)/'annotation-recognizer.onnx';self.session=None;self.lock=threading.RLock();atexit.register(self.stop)
 def ready(self):return self.path.is_file() and self.path.stat().st_size==MODEL_SIZE
 def read(self,image):
  with self.lock:
   if not self.ready():return None
   if self.session is None:
    if hashlib.sha256(self.path.read_bytes()).hexdigest()!=MODEL_SHA256:raise RuntimeError('The optional handwriting reader needs repair.')
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1;options.log_severity_level=3
    self.session=ort.InferenceSession(str(self.path),sess_options=options,providers=['CPUExecutionProvider'])
   import cv2
   rgb=np.asarray(image.convert('RGB'))[:,:,::-1];h,w=rgb.shape[:2];width=min(320,max(8,round(48*w/h)))
   data=cv2.resize(rgb,(width,48)).astype('float32')/127.5-1;canvas=np.zeros((1,3,48,320),np.float32);canvas[0,:,:,:width]=data.transpose(2,0,1)
   output=self.session.run(None,{self.session.get_inputs()[0].name:canvas})[0][0];indices=output.argmax(axis=1);characters=['blank']+CHARACTERS
   if characters[-1]!=' ':characters.append(' ')
   values=[];text=[];previous=-1
   for i,index in enumerate(indices):
    if index and index!=previous:
     if index>=len(characters):raise ValueError('Unexpected handwriting-reader dictionary.')
     text.append(characters[index]);values.append(float(output[i,index]))
    previous=index
   score=float(np.mean(values)) if values else 0
   return dict(text=''.join(text).strip(),score=score,model_sha256=MODEL_SHA256)
 def stop(self):
  with self.lock:self.session=None
_READERS={}
def reader_for(root):
 # Prefer a valid explicit cache; otherwise use the approved bundled asset.
 explicit=Path(root)
 bundle=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'/'handwriting'
 selected=explicit if (explicit/'annotation-recognizer.onnx').is_file() else bundle
 key=str(selected.resolve())
 if key not in _READERS:_READERS[key]=HandwritingReader(selected)
 return _READERS[key]
