import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont
from card_reading_views import stage_word,stage_word_readings

class CardDetailTests(unittest.TestCase):
 def test_stage_typography_is_bounded_and_does_not_repair_numbers(self):
  self.assertEqual(stage_word('fu!l',.8),'full');self.assertEqual(stage_word('Empty',.9),'empty')
  for text,score in [('fuel',.99),('fully',.99),('1/4 Full',.99),('3 Full',.99),('fu!l',.74),('LOAD #1',1)]:self.assertIsNone(stage_word(text,score))

 def test_nearby_fraction_ink_blocks_an_isolated_full_word(self):
  image=Image.new('RGB',(300,200),'#f4de62');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=28)
  draw.text((35,100),'1/4',fill='black',font=ImageFont.load_default(size=18));draw.text((160,100),'Full',fill='black',font=font)
  class Reader:
   def read(self,crop):
    # Only the full-width word proposal receives a stage-word reading.
    return dict(text='Full' if crop.width>55 else '1/4',score=.99)
  before=image.tobytes();self.assertEqual(stage_word_readings(image,Reader()),[]);self.assertEqual(image.tobytes(),before)

 def test_isolated_stage_word_retains_source_and_single_reader_status(self):
  image=Image.new('RGB',(300,200),'#f4de62');ImageDraw.Draw(image).text((130,100),'Full',fill='black',font=ImageFont.load_default(size=28))
  class Reader:
   def read(self,crop):return dict(text='fu!l',score=.9)
  before=image.tobytes();result=stage_word_readings(image,Reader());self.assertEqual(len(result),1);self.assertEqual(result[0]['text'],'Full');self.assertEqual(result[0]['loads'],[]);self.assertEqual(result[0]['engine'],'compact_handwriting');self.assertEqual(image.tobytes(),before)

 def test_card_detail_cycles_regions_and_fit_restores_context(self):
  import tkinter as tk
  from photo_inspector import PhotoPane
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'card.png';image=Image.new('RGB',(600,800),'#456789');ImageDraw.Draw(image).rectangle((240,320,300,400),fill='yellow');image.save(path);before=path.read_bytes()
   root=tk.Tk();root.geometry('800x700')
   try:
    pane=PhotoPane(root,path,card_regions=[dict(box=[.4,.4,.5,.5]),dict(box=[.1,.1,.2,.2])]);pane.pack(fill='both',expand=True);root.update();pane.fit();fitted=pane.scale
    pane.card_detail();self.assertGreater(pane.scale,fitted);self.assertFalse(pane.fit_mode);self.assertIn('1 / 2',pane.detail.cget('text'))
    pane.card_detail();self.assertIn('2 / 2',pane.detail.cget('text'));pane.fit();self.assertTrue(pane.fit_mode);self.assertAlmostEqual(pane.scale,fitted);self.assertEqual(path.read_bytes(),before)
   finally:root.destroy()

 def test_invalid_card_region_falls_back_without_changing_source(self):
  import tkinter as tk
  from photo_inspector import PhotoPane
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'card.png';Image.new('RGB',(200,200),'white').save(path);before=path.read_bytes();root=tk.Tk()
   try:
    pane=PhotoPane(root,path,card_regions=[dict(box=[-1,0,2,1]),dict(box=[0,0,float('nan'),1])]);pane.pack();root.update();pane.card_detail();self.assertIn('Locate the Card',pane.detail.cget('text'));self.assertEqual(path.read_bytes(),before)
   finally:root.destroy()
