"""Developer acceptance: interruption recovery, reachable dialogs and repeated use."""
import tempfile,unittest,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch


def widgets(parent):
 for child in parent.winfo_children():
  yield child
  yield from widgets(child)

class DeveloperWorkflowTests(unittest.TestCase):
 def setUp(self):
  import tkinter as tk
  from package_ui import PackageApp
  from test_cor_package import fixture
  self.root=tk.Tk();self.errors=[];self.root.report_callback_exception=lambda *a:self.errors.append(str(a[1]))
  self.tmp=tempfile.TemporaryDirectory();self.app=PackageApp(self.root);self.app.case_dir=Path(self.tmp.name);self.app.case=fixture(self.app.case_dir);self.app.start_photo_work=Mock();self.app.refresh();self.root.update()
 def tearDown(self):
  if hasattr(self.app._case_temp,'cleanup'):self.app._case_temp.cleanup()
  self.app._case_temp=None;self.root.destroy();self.tmp.cleanup();self.assertEqual(self.errors,[])
 def test_declining_incomplete_export_resumes_processing(self):
  self.app.evaluate=Mock(return_value=(0,0,0,['Missing evidence']))
  with patch('package_ui.messagebox.askyesno',return_value=False):self.app.generate()
  self.app.start_photo_work.assert_called_once()
 def test_cancelled_export_destination_resumes_processing(self):
  self.app._case_temp=object();self.app.evaluate=Mock(return_value=(0,0,0,[]))
  with patch('package_ui.filedialog.asksaveasfilename',return_value=''):self.app.generate()
  self.app.start_photo_work.assert_called_once()
 def test_cancelled_or_failed_export_resumes_processing(self):
  self.app.evaluate=Mock(return_value=(0,0,0,[]))
  for error in (InterruptedError('Cancelled'),OSError('Cannot write')):
   self.app.start_photo_work.reset_mock()
   with patch('background_task.run_file_task',side_effect=error),patch('package_ui.messagebox.showerror'):self.app.generate()
   self.app.start_photo_work.assert_called_once();self.assertFalse(self.app._file_task_running)
 def test_cancelled_close_resumes_current_case(self):
  with patch.object(self.app,'prepare_leave',return_value=False):self.app.close_app()
  self.assertTrue(self.root.winfo_exists());self.app.start_photo_work.assert_called_once()
 def test_project_save_failure_or_cancel_resumes_current_case(self):
  for error in (InterruptedError('Cancelled'),OSError('Cannot write')):
   self.app.start_photo_work.reset_mock()
   with patch('package_ui.filedialog.asksaveasfilename',return_value=str(Path(self.tmp.name)/'saved.edcase')),patch('background_task.run_file_task',side_effect=error),patch('package_ui.messagebox.showerror'):
    self.assertFalse(self.app.save_project())
   self.app.start_photo_work.assert_called_once()
 def test_refresh_does_not_accumulate_wheel_handlers(self):
  before=self.root.bind_all('<MouseWheel>')
  for _ in range(8):self.app.refresh();self.root.update()
  self.assertEqual(self.root.bind_all('<MouseWheel>'),before)
 def test_document_confirmation_remains_reachable_at_short_window(self):
  import tkinter as tk
  self.app.go(0);self.app.documents.selection_set('1');self.app.edit_document();self.root.update()
  win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Review Package Document');win.geometry('640x420');self.root.update()
  confirm=next(w for w in widgets(win) if w.winfo_class()=='TButton' and w.cget('text')=='Confirm Document')
  self.assertTrue(confirm.winfo_ismapped());self.assertLessEqual(confirm.winfo_rooty()+confirm.winfo_height(),win.winfo_rooty()+win.winfo_height())
 def test_unavailable_invoice_does_not_break_other_pages(self):
  invoice=next(d for d in self.app.case['package_documents'] if d['role']=='invoice');self.app.case['photo_text_cache']={invoice['path']:dict(text='INVOICE $100',sha256='stale')};Path(invoice['path']).unlink()
  self.app.refresh();self.root.update();self.assertTrue(self.app.case)
 def test_folder_import_keeps_ui_responsive_and_preserves_bytes(self):
  import time
  from PIL import Image
  import evidence_intake
  path=Path(self.tmp.name)/'new-photo.png';Image.new('RGB',(100,80),'yellow').save(path);original=path.read_bytes();ticks=[];stage=evidence_intake.stage_import
  def slow(*a,**k):time.sleep(.15);return stage(*a,**k)
  self.root.after(20,lambda:ticks.append(True))
  with patch('evidence_intake.stage_import',side_effect=slow),patch('package_ui.messagebox.showinfo'):
   self.assertTrue(self.app._import_paths([path]))
  self.assertTrue(ticks);record=next(r for r in self.app.case['imported_files'] if r.get('name')==path.name);self.assertEqual(Path(record['path']).read_bytes(),original);self.assertFalse(list(Path(self.tmp.name).glob('.ed-import-*')))
 def test_cancelled_add_document_does_not_register_or_open_a_dialog(self):
  path=next(d['path'] for d in self.app.case['package_documents'] if d['role']=='bid')
  with patch('package_ui.filedialog.askopenfilenames',return_value=(path,)),patch.object(self.app,'_import_paths',return_value=False),patch.object(self.app,'edit_document') as edit:
   self.app.add_bid();edit.assert_not_called()

 def test_changed_invoice_cannot_refill_empty_fields_from_old_suggestions(self):
  from calculator_evidence import file_digest
  invoice=next(d for d in self.app.case['package_documents'] if d['role']=='invoice');invoice['cost_suggestions']={'invoice_amount_usd':'9999'};invoice['cost_suggestions_sha256']=file_digest(invoice['path']);Path(invoice['path']).write_bytes(b'changed')
  self.app.case['invoice_amount_usd']='';self.app.vars={};self.app.refresh();self.root.update();self.assertEqual(self.app.vars['invoice_amount_usd'].get(),'')
 def test_invalid_optional_cache_does_not_crash_save_dialog(self):
  (self.app.case_dir/'local_photo_sorting.json').write_text('{bad')
  with patch('package_ui.filedialog.asksaveasfilename',return_value=''):self.assertFalse(self.app.save_project())
  self.app.start_photo_work.assert_called_once()

 def test_new_case_primary_action_is_visible_and_creates_the_entered_case(self):
  import tkinter as tk
  self.app.new_case();self.root.update()
  win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='New Case')
  create=next(w for w in widgets(win) if w.winfo_class()=='TButton' and w.cget('text')=='Create Case')
  self.assertTrue(create.winfo_ismapped(),'Create Case is hidden');self.assertLessEqual(create.winfo_rooty()+create.winfo_height(),win.winfo_rooty()+win.winfo_height())
  entries=[w for w in widgets(win) if w.winfo_class()=='TEntry']
  entries[0].insert(0,'NEW-CASE');entries[1].insert(0,'Synthetic Vendor');create.invoke();self.root.update()
  self.assertEqual(self.app.case['case_number'],'NEW-CASE');self.assertEqual(self.app.case['vendor'],'Synthetic Vendor');self.assertIsNotNone(self.app._case_temp)
 def test_long_progress_text_cannot_hide_cancel(self):
  import time,tkinter as tk
  from background_task import run_file_task
  checked=[]
  def inspect():
   win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Progress Test')
   cancel=next(w for w in widgets(win) if w.winfo_class()=='TButton' and w.cget('text')=='Cancel')
   checked.append(cancel.winfo_ismapped() and cancel.winfo_rooty()+cancel.winfo_height()<=win.winfo_rooty()+win.winfo_height())
  def work(cancel,progress):progress('Long synthetic file name '*30);time.sleep(.2);return True
  self.root.after(120,inspect);self.assertTrue(run_file_task(self.root,'Progress Test',work));self.assertEqual(checked,[True])

class ImportTransactionTests(unittest.TestCase):
 def test_cancel_mid_stream_leaves_existing_case_and_no_committed_files(self):
  from evidence_intake import stage_import
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'large.jpg';source.write_bytes(b'photo'*500000);stage=root/'stage';stage.mkdir();cancel=threading.Event()
   def progress(message):
    if message.startswith('Importing'):cancel.set()
   with self.assertRaises(InterruptedError):stage_import([source],set(),stage,cancel,progress)
   self.assertFalse(list(stage.iterdir()));self.assertEqual(source.stat().st_size,2500000)
 def test_zip_import_deduplicates_and_never_extracts_paths(self):
  import zipfile
  from evidence_intake import stage_import,commit_import
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);archive=root/'vendor.zip';stage=root/'stage';stage.mkdir()
   with zipfile.ZipFile(archive,'w') as z:z.writestr('../../escape.jpg',b'one');z.writestr('another.jpg',b'one');z.writestr('ignored.exe',b'no');z.writestr('oversized.jpg',b'123456')
   result=stage_import([archive],set(),stage,threading.Event(),lambda m:None,limit=5)
   self.assertEqual(len(result['records']),1);self.assertEqual(result['duplicates'],1);self.assertEqual(len(result['issues']),1)
   records,docs=commit_import(result,root/'originals');self.assertEqual(Path(records[0]['path']).parent,root/'originals');self.assertEqual(Path(records[0]['path']).read_bytes(),b'one');self.assertFalse((root/'escape.jpg').exists())
 def test_commit_failure_rolls_back_only_new_files(self):
  from evidence_intake import commit_import
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);stage=root/'stage';stage.mkdir();dest=root/'originals';dest.mkdir()
   a=stage/'a.jpg';a.write_bytes(b'a');b=stage/'b.jpg';b.write_bytes(b'b');old=dest/'b.jpg';old.write_bytes(b'original')
   result=dict(records=[dict(path=str(a),sha256='a'),dict(path=str(b),sha256='b')],documents=[])
   with self.assertRaises(ValueError):commit_import(result,dest)
   self.assertFalse((dest/'a.jpg').exists());self.assertEqual(old.read_bytes(),b'original')

class OptionalCacheRecoveryTests(unittest.TestCase):
 def test_invalid_optional_cache_does_not_prevent_project_round_trip(self):
  import json
  from portable_project import export_project,import_project
  from test_cor_package import fixture
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'source';source.mkdir();case=fixture(source);case['local_photo_results']={'retained':{'value':1}};(source/'local_photo_sorting.json').write_text('{broken')
   archive=root/'saved.edcase';export_project(case,source,archive);restored=root/'restored';import_project(archive,restored)
   self.assertEqual(json.loads((restored/'local_photo_sorting.json').read_text()),case['local_photo_results'])
