import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from portable_project import export_project,import_project,restored_data,fingerprint
from calculator_evidence import file_digest

class PortableProjectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.source=self.root/'source';self.source.mkdir();(self.source/'originals').mkdir()
  self.photo=self.source/'originals'/'photo.jpg';self.photo.write_bytes(b'original-photo')
  self.case=dict(case_number='TEST',loads=[dict(photos={'empty':str(self.photo)})],imported_files=[dict(path=str(self.photo))],property_stage_reviews={str(self.photo):dict(stage='before',sha256=file_digest(self.photo),source_mtime_ns=self.photo.stat().st_mtime_ns)})
 def tearDown(self):self.temp.cleanup()
 def test_template_selections_survive_project_reopen(self):
  self.case['template_photo_reviews']={'1:height':dict(path=str(self.photo),sha256=file_digest(self.photo),load=1,slot='height')}
  self.case['template_geometry_cache']={str(self.photo):dict(sha256=file_digest(self.photo),version=1,vertical=.5,horizontal=0)}
  self.case['template_photo_dismissals']={'1:width':{str(self.photo):dict(sha256=file_digest(self.photo))}}
  self.case['load_identity_cache']={str(self.photo):dict(sha256=file_digest(self.photo),status='corroborated',load=1)}
  self.case['load_sequence_anchors']={'1:start':dict(path=str(self.photo),sha256=file_digest(self.photo),sequence_time='2026-08-24T14:00:00')}
  target=self.root/'template.edcase';export_project(self.case,self.source,target)
  loaded=import_project(target,self.root/'restored-template');record=loaded['template_photo_reviews']['1:height']
  self.assertEqual(record['path'],str(self.root/'restored-template'/'originals'/'photo.jpg'))
  self.assertEqual(record['sha256'],file_digest(record['path']))
  self.assertEqual(loaded['template_geometry_cache'][record['path']]['vertical'],.5)
  self.assertEqual(loaded['template_photo_dismissals']['1:width'][record['path']]['sha256'],file_digest(record['path']))
  self.assertIn(record['path'],loaded['load_identity_cache']);self.assertEqual(loaded['load_sequence_anchors']['1:start']['path'],record['path'])
 def test_aliased_working_folder_fingerprints_and_reopens(self):
  alias=self.root/'alias'
  try:alias.symlink_to(self.source,target_is_directory=True)
  except (OSError,NotImplementedError):self.skipTest('Directory aliases require symlink permission.')
  path=alias/'originals'/'photo.jpg';case=dict(case_number='ALIAS',loads=[dict(photos={'empty':str(path)})],imported_files=[dict(path=str(path))])
  self.assertEqual(fingerprint(case,alias),fingerprint(case,self.source))
  target=self.root/'alias.edcase';export_project(case,alias,target)
  loaded=import_project(target,self.root/'restored-alias')
  self.assertEqual(Path(loaded['loads'][0]['photos']['empty']).read_bytes(),b'original-photo')
 def test_external_dismissed_source_is_rejected(self):
  self.case['template_photo_dismissals']={'1:width':{str(self.root/'outside.jpg'):dict(sha256='outside')}}
  with self.assertRaises(ValueError):export_project(self.case,self.source,self.root/'bad-dismissal.edcase')
 def test_external_template_review_source_is_rejected(self):
  self.case['template_photo_reviews']={'1:height':dict(path=str(self.root/'outside.jpg'))}
  with self.assertRaises(ValueError):export_project(self.case,self.source,self.root/'bad-template.edcase')
 def test_case_category_examples_survive_save_reopen_with_rebased_paths(self):
  self.case['photo_category_examples']={str(self.photo):dict(category='documents',sha256=file_digest(self.photo))}
  target=self.root/'categories.edcase';export_project(self.case,self.source,target)
  loaded=import_project(target,self.root/'restored-categories')
  p=str(self.root/'restored-categories'/'originals'/'photo.jpg')
  self.assertEqual(loaded['photo_category_examples'][p]['category'],'documents')
  self.assertEqual(loaded['photo_category_examples'][p]['sha256'],file_digest(p))
 def test_external_category_reference_is_not_silently_saved(self):
  self.case['photo_category_examples']={str(self.root/'outside.jpg'):dict(category='documents',sha256='x')}
  with self.assertRaises(ValueError):export_project(self.case,self.source,self.root/'bad.edcase')
 def test_export_open_rebases_paths_originals_and_cache(self):
  cache={str(self.photo):{'sha256':file_digest(self.photo)}};(self.source/'local_photo_sorting.json').write_text(json.dumps(cache))
  (self.source/'output').mkdir();(self.source/'output'/'finished.pdf').write_bytes(b'pdf')
  saved=self.root/'test.edcase';export_project(self.case,self.source,saved)
  opened=self.root/'another-computer';case=import_project(saved,opened);photo=Path(case['loads'][0]['photos']['empty'])
  self.assertEqual(photo.read_bytes(),b'original-photo');self.assertTrue(photo.is_relative_to(opened));self.assertIn(str(photo),case['property_stage_reviews'])
  self.assertFalse((opened/'output').exists());self.assertIn(str(photo),json.loads((opened/'local_photo_sorting.json').read_text()))
 def test_save_failure_preserves_previous_project(self):
  saved=self.root/'test.edcase';saved.write_bytes(b'previous')
  with self.assertRaises(ValueError):export_project(self.case,self.source,self.source/'nested.edcase')
  self.assertEqual(saved.read_bytes(),b'previous')
 def test_load_album_and_feature_cache_survive_project_move(self):
  self.case['photo_load_assignments']={str(self.photo):dict(load=1,sha256=file_digest(self.photo))}
  cache={str(self.photo):dict(sha256=file_digest(self.photo),features={'version':1},prediction={'embedding':'preserved'})}
  (self.source/'local_photo_sorting.json').write_text(json.dumps(cache))
  saved=self.root/'test.edcase';export_project(self.case,self.source,saved)
  opened=self.root/'moved';case=import_project(saved,opened);path=case['imported_files'][0]['path']
  self.assertEqual(case['photo_load_assignments'][path]['load'],1)
  restored=json.loads((opened/'local_photo_sorting.json').read_text())
  self.assertEqual(restored[path]['prediction']['embedding'],'preserved')
 def test_unsafe_archive_does_not_write_outside_workspace(self):
  saved=self.root/'bad.edcase'
  with zipfile.ZipFile(saved,'w') as z:z.writestr('../escape',b'bad')
  with self.assertRaises(ValueError):import_project(saved,self.root/'opened')
  self.assertFalse((self.root/'escape').exists())
 def test_unsafe_json_file_reference_rejected(self):
  with self.assertRaises(ValueError):restored_data({'file':'@edcase/../outside'},self.root)

if __name__=='__main__':unittest.main()
