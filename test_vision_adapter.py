import unittest,tempfile
from pathlib import Path
from PIL import Image
from vision_adapter import parse_response,prepare_image,suggest_load_links
class TestVision(unittest.TestCase):
 def test_invalid_prediction_is_unverified(self):
  x=parse_response('```json\n{"category":"imaginary","stage":"85%","load_number":-2}\n```')
  self.assertEqual(x['category'],'unclear');self.assertEqual(x['stage'],'unknown');self.assertIsNone(x['load_number']);self.assertFalse(x['verified'])
 def test_valid(self):
  x=parse_response({'category':'dump_receipt','stage':'unknown','load_number':2,'receipt_id':'R-20'})
  self.assertEqual(x['load_number'],2);self.assertEqual(x['receipt_id'],'R-20')
 def test_image_encoding(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'photo.png';Image.new('RGB',(2400,900)).save(p)
   self.assertGreater(len(prepare_image(p)),100)
 def test_links_are_suggestions(self):
  x=suggest_load_links([{'prediction':{'load_number':3,'verified':False}}]);self.assertIn(3,x)
if __name__=='__main__':unittest.main()
