import tempfile,unittest
from pathlib import Path
from evidence_audit import collect,write_report
class AuditTests(unittest.TestCase):
 def test_unassigned_files_block(self):
  r=collect({'loads':[{'photos':{}}]})
  self.assertGreaterEqual(r['blocking'],11)
 def test_cross_load_and_missing_file(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'photo.jpg';p.write_bytes(b'fake image')
   c={'case_number':'test','loads':[{'photos':{'empty':str(p)}},{'photos':{'empty':str(p)}}]}
   r=write_report(c,Path(d)/'report')
   self.assertIn('cross_load_reuse',[x['type'] for x in r['issues']])
   self.assertTrue((Path(d)/'report'/'Evidence_Audit.csv').exists())
 def test_byte_identical_separate_paths(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.jpg';b=Path(d)/'b.jpg';a.write_bytes(b'same');b.write_bytes(b'same')
   r=collect({'loads':[{'photos':{'empty':str(a)}},{'photos':{'empty':str(b)}}]})
   self.assertIn('identical_content_cross_load',[x['type'] for x in r['issues']])
 def test_missing_link(self):
  r=collect({'loads':[{'photos':{'empty':'/tmp/ED_FAKE_DOES_NOT_EXIST/photo.jpg'}}]})
  self.assertIn('file_missing',[x['type'] for x in r['issues']])
if __name__=='__main__':unittest.main()
