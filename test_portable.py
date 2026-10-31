import unittest,tempfile,zipfile
from pathlib import Path
from pilot_preflight import audit_archive
class TestPortable(unittest.TestCase):
 def test_safe_archive(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('sub/a.jpg',b'abc');z.writestr('b.pdf',b'xyz')
   result=audit_archive(p)
   self.assertEqual(result['images'],1)
   self.assertEqual(result['total_files'],2)
 def test_bad_archive(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('../unsafe.jpg',b'foo')
   with self.assertRaises(ValueError):audit_archive(p)
