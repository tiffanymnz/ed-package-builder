import unittest,threading
from PIL import Image,ImageDraw,ImageFont
from card_fractions import propose_half

class FractionShapeTests(unittest.TestCase):
 def make_card(self,kind='half',extra=False):
  image=Image.new('RGB',(320,320),'white');d=ImageDraw.Draw(image)
  # Same generic written layout, with separate numeral, long divider and denominator.
  d.text((20,20),'LOAD 2',fill='black')
  d.line((102,121,104,151),fill='black',width=3)
  if kind!='twelve':d.line((120,120,120,194),fill='black',width=3)
  if kind in ('half','twelve'):
   points=[(134,156),(139,151),(148,150),(151,154),(150,160),(135,173),(135,176),(166,169)]
   if kind=='twelve':points=[(x,y-30) for x,y in points]
   d.line(points,fill='black',width=3)
  else:
   font=ImageFont.load_default(size=32)
   d.text((132,145),kind,fill='black',font=font)
  if extra:d.text((200,155),'FT',fill='black')
  return image
 def test_isolated_fraction_shape_is_suggestion_only(self):
  found=propose_half(self.make_card());self.assertEqual(len(found),1);self.assertEqual(found[0]['stage'],'half');self.assertFalse(found[0]['verified'])
 def test_plain_twelve_has_no_fraction_divider(self):self.assertEqual(propose_half(self.make_card('twelve')),[])
 def test_one_fourth_is_not_read_as_half(self):self.assertEqual(propose_half(self.make_card('4')),[])
 def test_one_third_is_not_read_as_half(self):self.assertEqual(propose_half(self.make_card('3')),[])
 def test_equation_or_unit_text_is_not_a_standalone_stage(self):self.assertEqual(propose_half(self.make_card(extra=True)),[])
 def test_letter_z_is_not_a_readable_denominator_two(self):self.assertEqual(propose_half(self.make_card('Z')),[])
 def test_one_seventh_is_not_read_as_half(self):self.assertEqual(propose_half(self.make_card('7')),[])
 def test_small_unreadable_crop_abstains(self):self.assertEqual(propose_half(self.make_card().resize((40,40))),[])

class FractionEvidenceTests(unittest.TestCase):
 def test_conflicting_literal_full_is_not_overridden_by_half_shape(self):
  import tempfile
  from pathlib import Path
  from calculator_evidence import file_digest
  from load_identity import VERSION
  from load_text_runtime import MODEL_DIGEST
  from card_evidence import stage_claim
  with tempfile.TemporaryDirectory() as folder:
   p=str(Path(folder)/'card.png');Image.new('RGB',(100,100),'white').save(p);sha=file_digest(p)
   entry=dict(version=VERSION,model_digest=MODEL_DIGEST,sha256=sha,status='single_reader',options=[2],readings=[dict(text='LOAD 2\nFull')],fraction_readings=[dict(stage='half',version=1,box=[.1,.2,.3,.5])])
   self.assertIsNone(stage_claim(dict(load_identity_cache={p:entry}),p))
 def test_twelve_text_without_shape_is_not_half(self):
  import tempfile
  from pathlib import Path
  from calculator_evidence import file_digest
  from load_identity import VERSION
  from load_text_runtime import MODEL_DIGEST
  from card_evidence import stage_claim
  with tempfile.TemporaryDirectory() as folder:
   p=str(Path(folder)/'card.png');Image.new('RGB',(100,100),'white').save(p);sha=file_digest(p)
   entry=dict(version=VERSION,model_digest=MODEL_DIGEST,sha256=sha,status='single_reader',options=[2],readings=[dict(text='LOAD 2\n12')])
   self.assertIsNone(stage_claim(dict(load_identity_cache={p:entry}),p))
