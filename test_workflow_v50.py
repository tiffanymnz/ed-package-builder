import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from calculator_evidence import file_digest
from review_actions import snapshot,remember,undo
from invoice_review import use_invoice_version,confirm_invoice_set,issues
from trip_bounds import confirm_trip_bounds,review_windows
from export_bundle import recover_bundles

class WorkflowUpgradeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.paths=[]
  from PIL import Image
  for n in range(4):
   p=self.root/f'{n}.png';Image.new('RGB',(80,60),(n*40,70,90)).save(p);self.paths.append(str(p))
  self.case=dict(loads=[{'photos':{}},{'photos':{}}],imported_files=[dict(path=p) for p in self.paths])
 def row(self,n,clock,category='container_photos',source='photo_text',load=None):
  p=self.paths[n];return dict(path=p,sha256=file_digest(p),sequence_time=clock,sequence_source=source,category=category,stage='review',load=load)
 def invoices(self):
  self.case['package_documents']=[dict(path=p,role='invoice',confirmed=True,reviewed_sha256=file_digest(p)) for p in self.paths[:2]]
 def test_undo_preserves_worker_cache(self):
  before=snapshot(self.case);self.case['photo_load_assignments']={self.paths[0]:{'load':1}};action=remember(self.case,before,self.paths[:1],'load');self.case['local_photo_results']={'worker':'new'}
  undo(self.case,action);self.assertNotIn('photo_load_assignments',self.case);self.assertEqual(self.case['local_photo_results'],{'worker':'new'})
 def test_undo_rejects_later_review_without_mutation(self):
  before=snapshot(self.case);self.case['photo_load_assignments']={self.paths[0]:{'load':1}};action=remember(self.case,before,self.paths[:1],'load');self.case['before_photos']=self.paths[:1];expected=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):undo(self.case,action)
  self.assertEqual(expected,self.case)
 def test_undo_rejects_changed_source(self):
  before=snapshot(self.case);self.case['before_photos']=self.paths[:1];action=remember(self.case,before,self.paths[:1],'stage');Path(self.paths[0]).write_bytes(b'changed')
  with self.assertRaises(ValueError):undo(self.case,action)
 def test_final_invoice_selection_keeps_original(self):
  self.invoices();self.case['financial_confirmation_hash']='old';use_invoice_version(self.case,1)
  self.assertEqual([d['role'] for d in self.case['package_documents']],['exclude','invoice']);self.assertTrue(Path(self.paths[0]).exists());self.assertNotIn('financial_confirmation_hash',self.case)
 def test_combined_invoice_set_is_explicit_and_source_bound(self):
  self.invoices();self.assertTrue(issues(self.case));confirm_invoice_set(self.case);self.assertFalse(issues(self.case));Path(self.paths[0]).write_bytes(b'changed');self.assertTrue(issues(self.case))
 def test_unreviewed_final_invoice_does_not_change_roles(self):
  self.invoices();self.case['package_documents'][1]['confirmed']=False;before=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):use_invoice_version(self.case,1)
  self.assertEqual(before,self.case)
 def endpoints(self):return [self.row(0,'2026-08-24T14:00:00'),self.row(1,'2026-08-24T14:30:00')]
 def test_trip_window_is_review_only_never_template_placement(self):
  ends=self.endpoints();confirm_trip_bounds(self.case,ends,1)
  for r in ends:r['load']=1
  middle=self.row(2,'2026-08-24T14:10:00','other');result=review_windows(self.case,ends+[middle])[middle['path']]
  self.assertIsNone(result['load']);self.assertTrue(result['review_only']);self.assertEqual(result['candidate_load'],1);self.assertEqual(self.case['loads'][0]['photos'],{})
 def test_date_only_endpoints_reject_atomically(self):
  ends=self.endpoints();ends[1]['sequence_time']=None;before=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):confirm_trip_bounds(self.case,ends,1)
  self.assertEqual(before,self.case)
 def test_changed_endpoint_rejects_atomically(self):
  ends=self.endpoints();Path(self.paths[1]).write_bytes(b'new');before=copy.deepcopy(self.case)
  with self.assertRaises(ValueError):confirm_trip_bounds(self.case,ends,1)
  self.assertEqual(before,self.case)
 def test_window_does_not_capture_property_documents_or_extrapolate(self):
  ends=self.endpoints();confirm_trip_bounds(self.case,ends,1)
  for r in ends:r['load']=1
  for category,clock,source in [('property_photos','2026-08-24T14:10:00','photo_text'),('documents','2026-08-24T14:10:00','photo_text'),('other','2026-08-24T14:31:00','photo_text'),('other','2026-08-24T14:10:00','camera')]:
   mid=self.row(2,clock,category,source);self.assertNotIn(mid['path'],review_windows(self.case,ends+[mid]))
 def test_process_exit_during_export_recovers_previous_bundle(self):
  for name,data in [('out.pdf',b'old pdf'),('out.txt',b'old text'),('new.pdf',b'new pdf'),('new.txt',b'new text')]: (self.root/name).write_bytes(data)
  script="""import os,sys
from pathlib import Path
import export_bundle as e
r=Path(sys.argv[1]);original=e.os.replace
calls=0
def crash(a,b):
 global calls
 original(a,b);calls+=1
 if calls==1:os._exit(71)
e.os.replace=crash
e.publish_bundle([(r/'out.pdf',r/'new.pdf'),(r/'out.txt',r/'new.txt')])
"""
  result=subprocess.run([sys.executable,'-c',script,str(self.root)],cwd=Path(__file__).parent)
  self.assertEqual(result.returncode,71);self.assertEqual(recover_bundles(self.root),1);self.assertEqual((self.root/'out.pdf').read_bytes(),b'old pdf');self.assertEqual((self.root/'out.txt').read_bytes(),b'old text')
 def journal(self,name='out.pdf',bad=False):
  stage=self.root/'.ed-publish-test';stage.mkdir();(stage/'0').write_bytes(b'backup');(stage/'READY').write_text('ready');(stage/'journal.json').write_text(json.dumps([dict(name=name,backup='0',sha256='wrong' if bad else file_digest(stage/'0'))]));return stage
 def test_corrupt_recovery_backup_preserves_existing_output(self):
  target=self.root/'out.pdf';target.write_bytes(b'keep');self.journal(bad=True)
  with self.assertRaises(ValueError):recover_bundles(self.root)
  self.assertEqual(target.read_bytes(),b'keep')
 def test_unsafe_recovery_destination_is_rejected(self):
  self.journal('../outside')
  with self.assertRaises(ValueError):recover_bundles(self.root)
 def test_split_load_labels_are_bounded(self):
  from load_identity import text_numbers
  self.assertEqual(text_numbers('Truck (1)\nLoad\n(2)\nHalf'),[2]);self.assertEqual(text_numbers('Load\n2 x 7 ft'),[]);self.assertEqual(text_numbers('Total\n2'),[]);self.assertEqual(text_numbers('Load\n2.5'),[])
