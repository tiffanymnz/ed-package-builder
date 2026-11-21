"""Public synthetic regressions for issues found during private acceptance."""
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw,ImageFont

class ReleaseAcceptanceTests(unittest.TestCase):
 def test_a_false_card_region_does_not_suppress_whole_photo_reading(self):
  from load_identity import read_load_card
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'scene.png';Image.new('RGB',(400,300),'white').save(path)
   runtime=Mock(root=Path(folder));runtime.read.side_effect=[dict(text='Unknown'),dict(text='LOAD 2\nFULL'),dict(text='LOAD 2')]
   with patch('card_regions.locate_cards',return_value=[dict(box=[.1,.1,.5,.5])]),patch('card_regions.card_crops',return_value=[Image.new('RGB',(150,100),'white')]),patch('annotation_panels.annotation_panel',return_value=None),patch('local_reader.read_image',return_value=('','')),patch('load_identity.regions',side_effect=lambda text:[dict(text=text)]),patch('card_fractions.propose_half',return_value=[]):
    result=read_load_card(path,'',threading.Event(),runtime)
   self.assertEqual(result['options'],[2]);self.assertEqual(result['status'],'single_reader')
   self.assertEqual(result['stage_reading']['stage'],'full')
   self.assertIsNone(result['load'])

 def test_yellow_paper_with_ink_is_a_region_candidate(self):
  from card_regions import locate_cards
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'yellow.png';image=Image.new('RGB',(640,480),'#325968');draw=ImageDraw.Draw(image)
   draw.rectangle((390,235,585,450),fill='#f4dc55');font=ImageFont.load_default(size=30)
   for y,text in [(255,'LOAD 2'),(315,'Empty'),(375,'Debris')]:draw.text((405,y),text,font=font,fill='black')
   image.save(path);regions=locate_cards(path)
   self.assertTrue(any(r['box'][0]<.76<r['box'][2] and r['box'][1]<.7<r['box'][3] for r in regions))

 def test_blank_yellow_rectangle_does_not_establish_a_card(self):
  from card_regions import locate_cards
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'blank.png';image=Image.new('RGB',(640,480),'#325968');ImageDraw.Draw(image).rectangle((390,235,585,450),fill='#f4dc55');image.save(path)
   self.assertEqual(locate_cards(path),[])

 def test_garden_control_preserves_measurement_text_features(self):
  import measurement_controls as controls
  for vector in controls._MEASUREMENT:self.assertTrue(controls.supports_measurement(vector))
  for vector in controls._GARDEN:self.assertFalse(controls.supports_measurement(vector))

if __name__=='__main__':unittest.main()
