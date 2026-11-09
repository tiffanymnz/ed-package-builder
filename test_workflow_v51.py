import copy,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import numpy as np
from calculator_evidence import file_digest
class ReviewAssistanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.case={'imported_files':[],'loads':[{'photos':{}}]};self.rows=[]
  for i in range(5):
   p=self.root/f'{i}.png';Image.new('RGB',(80,60),(i*30,40,80)).save(p);self.case['imported_files'].append({'path':str(p)});v=np.zeros(512,np.float32);v[0]=1
   self.rows.append(dict(path=str(p),sha256=file_digest(p),category='container_photos',embedding=v,sequence_date='2026-07-19',load=None,stage='review'))
 def test_related_group_never_assigns_trip_stage_or_box(self):
  from related_review import related_groups
  before=copy.deepcopy(self.case);out=related_groups(self.case,self.rows);self.assertEqual(len(out),5);self.assertEqual(before,self.case)
  for p in out.values():self.assertTrue(p['review_only']);self.assertIsNone(p['load']);self.assertFalse(p['verified'])
 def test_date_and_category_boundaries_do_not_merge(self):
  from related_review import related_groups
  self.rows[3]['sequence_date']='2026-07-20';self.rows[4]['category']='property_photos';out=related_groups(self.case,self.rows);self.assertEqual(set(out),{r['path'] for r in self.rows[:3]})
 def test_changed_sources_and_financial_documents_are_excluded(self):
  from related_review import related_groups
  Path(self.rows[4]['path']).write_bytes(b'changed');self.case['package_documents']=[dict(path=self.rows[3]['path'],role='invoice',confirmed=True)];out=related_groups(self.case,self.rows);self.assertEqual(set(out),{r['path'] for r in self.rows[:3]})
 def test_reviewed_photos_anchor_groups_without_being_reviewed_again(self):
  from related_review import related_groups
  self.rows[0]['load']=1;out=related_groups(self.case,self.rows);self.assertNotIn(self.rows[0]['path'],out);self.assertEqual(len(out),4)
 def test_visual_chaining_does_not_pull_in_unrelated_tail(self):
  from related_review import related_groups
  ordered=sorted(self.rows,key=lambda r:r['sha256']);ordered[3]['embedding'][:2]=[.9,np.sqrt(1-.9**2)];ordered[4]['embedding'][:2]=[.7,np.sqrt(1-.7**2)]
  out=related_groups(self.case,self.rows);self.assertNotIn(ordered[4]['path'],out)
 def test_stage_only_text_is_usable_without_a_load_number(self):
  from load_identity import VERSION
  from load_text_runtime import MODEL_DIGEST
  from card_evidence import stage_claim
  p=self.rows[0]['path'];self.case['load_identity_cache']={p:dict(sha256=file_digest(p),version=VERSION,model_digest=MODEL_DIGEST,status='no_clue',options=[],readings=[dict(engine='standard',text='Full')],annotation_panel=dict(kind='annotation_panel'))}
  claim=stage_claim(self.case,p);self.assertEqual(claim['stage'],'full');self.assertTrue(claim['scene_context']);self.assertEqual(self.case['loads'][0]['photos'],{})
 def test_literal_stage_parser_rejects_dimensions_and_plain_digits(self):
  from stage_text import stages,evidence
  for text in ('12','14','1/4 ft','Total 1/2','Full payment received'):self.assertEqual(stages(text),[])
  self.assertEqual(stages('½'),['half']);self.assertEqual(evidence([dict(engine='a',text='1/4'),dict(engine='b',text='Full')])['status'],'conflict')
 def test_extra_model_is_not_downloaded_or_required_by_default(self):
  from handwriting_reader import HandwritingReader
  reader=HandwritingReader(self.root)
  with patch('onnxruntime.InferenceSession') as session:self.assertIsNone(reader.read(Image.new('RGB',(100,50),'white')));session.assert_not_called()
  from load_text_runtime import ASSETS
  self.assertEqual(sum(a['size'] for a in ASSETS),277470179)
class FractionGeometryTests(unittest.TestCase):
 def test_plain_digits_and_blank_images_do_not_become_fractions(self):
  from PIL import ImageDraw
  from annotation_panels import linearize_fraction
  for label in ('','12','14','Full'):
   image=Image.new('RGB',(240,100),'white');ImageDraw.Draw(image).text((15,15),label,fill='black',font_size=60)
   original=image.tobytes();self.assertIsNone(linearize_fraction(image));self.assertEqual(image.tobytes(),original)
 def test_fraction_alignment_does_not_modify_source(self):
  from PIL import ImageDraw
  from annotation_panels import linearize_fraction
  image=Image.new('RGB',(240,180),'white');draw=ImageDraw.Draw(image)
  draw.rectangle((20,20,30,80),fill='black');draw.line((60,140,120,15),fill='black',width=7);draw.rectangle((150,100,180,165),fill='black')
  original=image.tobytes();self.assertIsNotNone(linearize_fraction(image));self.assertEqual(image.tobytes(),original)
class ExportIntegrityTests(unittest.TestCase):
 def test_silent_corruption_restores_previous_files(self):
  from export_bundle import publish_bundle
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);pdf=root/'out.pdf';text=root/'out.txt';src=root/'new.pdf';note=root/'new.txt'
   for p,v in [(pdf,b'old pdf'),(text,b'old text'),(src,b'new pdf'),(note,b'new text')]:p.write_bytes(v)
   original=os.replace;corrupted=False
   def replace(a,b):
    nonlocal corrupted
    original(a,b)
    if Path(b)==pdf and not corrupted:Path(b).write_bytes(b'corrupt');corrupted=True
   with patch('export_bundle.os.replace',side_effect=replace):
    with self.assertRaises(RuntimeError):publish_bundle([(pdf,src),(text,note)])
   self.assertEqual(pdf.read_bytes(),b'old pdf');self.assertEqual(text.read_bytes(),b'old text')
 def test_concurrent_export_cannot_touch_previous_pdf(self):
  from export_bundle import folder_lock,publish_bundle
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);out=root/'out.pdf';out.write_bytes(b'old');new=root/'new.pdf';new.write_bytes(b'new')
   with folder_lock(root):
    with self.assertRaisesRegex(RuntimeError,'Another export'):publish_bundle([(out,new)])
   self.assertEqual(out.read_bytes(),b'old')

class BundledHandwritingTests(unittest.TestCase):
 def test_bundled_asset_has_pinned_hash_and_license(self):
  import hashlib,handwriting_reader
  assets=Path(handwriting_reader.__file__).parent/'assets'/'handwriting'
  model=assets/'annotation-recognizer.onnx'
  self.assertEqual(model.stat().st_size,handwriting_reader.MODEL_SIZE)
  self.assertEqual(hashlib.sha256(model.read_bytes()).hexdigest(),handwriting_reader.MODEL_SHA256)
  self.assertIn('Apache License',(assets/'LICENSE.txt').read_text())
 def test_default_reader_uses_bundle_without_copy_or_download(self):
  import handwriting_reader
  with tempfile.TemporaryDirectory() as folder:
   reader=handwriting_reader.reader_for(folder)
   self.assertTrue(reader.ready());self.assertFalse((Path(folder)/'annotation-recognizer.onnx').exists())
