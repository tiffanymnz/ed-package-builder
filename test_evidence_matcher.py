import unittest,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from evidence_matcher import rank_similar
class TestMatching(unittest.TestCase):
 def test_similar_returns_same_subject_and_excludes_self(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d)
   img=Image.new('RGB',(320,200),'gray');ImageDraw.Draw(img).rectangle((20,30,260,165),fill='brown')
   img.save(d/'a.jpg',quality=92);img.save(d/'a_repeat.jpg',quality=70)
   Image.new('RGB',(320,200),'blue').save(d/'different.jpg')
   rows=[{'path':str(p)} for p in d.glob('*.jpg')]
   matches=rank_similar(d/'a.jpg',rows)
   self.assertEqual(matches[0]['name'],'a_repeat.jpg')
   self.assertEqual(len(matches),2)
   self.assertTrue(matches[0]['possible_repeat'])
if __name__=='__main__':unittest.main()
