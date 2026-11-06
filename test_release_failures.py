import copy,tempfile,unittest,os,json
from pathlib import Path
from unittest.mock import patch
from export_bundle import publish_bundle

class ExportFailureTests(unittest.TestCase):
 def test_sidecar_write_failure_restores_entire_previous_bundle(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);pdf=root/'out.pdf';desc=root/'out.txt';src=root/'new.pdf';text=root/'new.txt'
   for path,value in [(pdf,b'old pdf'),(desc,b'old text'),(src,b'new pdf'),(text,b'new text')]:path.write_bytes(value)
   replace=os.replace;calls=[]
   def fail_second(a,b):
    calls.append(str(b))
    if len(calls)==2:raise PermissionError('simulated locked description')
    return replace(a,b)
   with patch('export_bundle.os.replace',side_effect=fail_second):
    with self.assertRaises(PermissionError):publish_bundle([(pdf,src),(desc,text)])
   self.assertEqual(pdf.read_bytes(),b'old pdf');self.assertEqual(desc.read_bytes(),b'old text')
   self.assertFalse(list(root.glob('.ed-publish-*')))
 def test_incomplete_export_removes_stale_external_description(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);pdf=root/'out.pdf';desc=root/'out.description.txt';src=root/'new.pdf';src.write_bytes(b'new pdf');pdf.write_bytes(b'old');desc.write_text('old payable description')
   publish_bundle([(pdf,src),(desc,None)])
   self.assertEqual(pdf.read_bytes(),b'new pdf');self.assertFalse(desc.exists())
 def test_alias_destinations_cannot_overwrite_each_other(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'child').mkdir();target=root/'out.pdf';target.write_bytes(b'previous');source=root/'new.pdf';source.write_bytes(b'new')
   with self.assertRaises(ValueError):publish_bundle([(target,source),(root/'child'/'..'/'out.pdf',None)])
   self.assertEqual(target.read_bytes(),b'previous')
 def test_unreadable_input_preserves_existing_outputs(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);pdf=root/'out.pdf';pdf.write_bytes(b'old')
   with self.assertRaises(FileNotFoundError):publish_bundle([(pdf,root/'missing')])
   self.assertEqual(pdf.read_bytes(),b'old')
 def test_assemble_report_failure_keeps_previous_pdf_and_description(self):
  import cor_package
  from test_cor_package import fixture
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);case=fixture(root);pdf=root/'out.pdf';pdf.write_bytes(b'old pdf');review=root/'Package_Review.json';review.write_text('old report');desc=root/'COR_Request_Description.txt';desc.write_text('old text')
   replace=os.replace;failed=False
   def fail_report(a,b):
    nonlocal failed
    if Path(b).resolve()==review.resolve() and not failed:failed=True;raise PermissionError('report locked')
    return replace(a,b)
   with patch('export_bundle.os.replace',side_effect=fail_report):
    with self.assertRaises(PermissionError):cor_package.assemble(case,pdf)
   self.assertTrue(failed,'The simulated output failure was not injected')
   self.assertEqual(pdf.read_bytes(),b'old pdf');self.assertEqual(review.read_text(),'old report');self.assertEqual(desc.read_text(),'old text')

class ProjectFailureTests(unittest.TestCase):
 def test_changed_source_during_save_does_not_replace_previous_project(self):
  from portable_project import export_project
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'working';root.mkdir();photo=root/'photo.jpg';photo.write_bytes(b'original')
   case=dict(case_number='TEST',loads=[{'photos':{}}],imported_files=[dict(path=str(photo))]);dest=Path(folder)/'saved.edcase';dest.write_bytes(b'previous project')
   def progress(text):
    if text.startswith('Saving File'):photo.write_bytes(b'changed after manifest')
   with self.assertRaises(ValueError):export_project(case,root,dest,progress=progress)
   self.assertEqual(dest.read_bytes(),b'previous project')
 def test_missing_first_ten_file_is_reported(self):
  from test_cor_package import fixture
  from cor_package import validate
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case['loads'][0]['evidence_first_10_cyd']='not-there.jpg'
   self.assertIn('Add the first-10-CYD evidence.',validate(case))
