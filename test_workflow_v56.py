import copy,queue,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PIL import Image
from calculator_evidence import file_digest

class InlineThread:
 def __init__(self,target,**kwargs):self.target=target
 def start(self):self.target()

class ReaderRecoveryTests(unittest.TestCase):
 def test_retry_keeps_successful_attempts_and_recovers_failed_and_unstarted_cards(self):
  from photo_flow import BackgroundPhotoWork
  with tempfile.TemporaryDirectory() as folder:
   records=[];sources={}
   for i in range(3):
    p=Path(folder)/f'{i}.png';Image.new('RGB',(100,80),'white').save(p);records.append(dict(path=str(p)));sources[str(p)]=dict(sha256=file_digest(p),card_regions=[dict(box=[.1,.1,.5,.5])])
   case=dict(imported_files=records,local_photo_results=sources,photo_text_cache={})
   worker=SimpleNamespace(case=case,app=SimpleNamespace(case=case),closed=False,cancel=threading.Event(),reader_running=False,load_failure=False,priority=[],load_attempted=set(),events=queue.Queue(),changed=False)
   with patch('photo_flow.threading.Thread',InlineThread),patch('load_identity.card_candidate',return_value=True),patch('load_text_runtime.RUNTIME.ready',return_value=True),patch('load_identity.read_load_card',side_effect=[dict(options=[1],status='single_reader'),RuntimeError('temporary failure')]) as reader:
    BackgroundPhotoWork.read_loads(worker);self.assertEqual(reader.call_count,2)
   self.assertTrue(worker.load_failure);self.assertTrue(BackgroundPhotoWork.retry_reading(worker));self.assertEqual(len(worker.load_attempted),1)
   with patch('photo_flow.threading.Thread',InlineThread),patch('load_identity.card_candidate',return_value=True),patch('load_text_runtime.RUNTIME.ready',return_value=True),patch('load_identity.read_load_card',return_value=dict(options=[2],status='single_reader')) as reader:
    BackgroundPhotoWork.read_loads(worker);self.assertEqual([v.args[0] for v in reader.call_args_list],[r['path'] for r in records[1:]])
   self.assertEqual(len(worker.load_attempted),3)
 def test_reader_cancellation_is_handled_without_a_false_failure(self):
  from photo_flow import BackgroundPhotoWork
  from small_vision_runtime import SetupCancelled
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'card.png';Image.new('RGB',(100,80),'white').save(p);case=dict(imported_files=[dict(path=str(p))],local_photo_results={str(p):dict(sha256=file_digest(p),card_regions=[dict(box=[.1,.1,.5,.5])])},photo_text_cache={})
   worker=SimpleNamespace(case=case,cancel=threading.Event(),reader_running=False,load_failure=False,priority=[],load_attempted=set(),events=queue.Queue())
   with patch('photo_flow.threading.Thread',InlineThread),patch('load_identity.card_candidate',return_value=True),patch('load_text_runtime.RUNTIME.ready',return_value=True),patch('load_identity.read_load_card',side_effect=SetupCancelled()):BackgroundPhotoWork.read_loads(worker)
   self.assertFalse(worker.load_failure);self.assertFalse(worker.reader_running)
 def test_retry_cannot_resume_another_case_or_a_cancelled_worker(self):
  from photo_flow import BackgroundPhotoWork
  case={};worker=SimpleNamespace(case=case,app=SimpleNamespace(case={}),closed=False,reader_running=False,load_failure=True,cancel=threading.Event())
  self.assertFalse(BackgroundPhotoWork.retry_reading(worker));worker.app.case=case;worker.cancel.set();self.assertFalse(BackgroundPhotoWork.retry_reading(worker))

class WorkflowUiTests(unittest.TestCase):
 def setUp(self):
  import tkinter as tk
  from package_ui import PackageApp
  from ed_app import make_case
  self.root=tk.Tk();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(str(args[1]));self.tmp=tempfile.TemporaryDirectory();self.app=PackageApp(self.root);self.app.case=make_case('TEST','','Vendor',2,35);self.app.case_dir=Path(self.tmp.name);self.app.start_photo_work=Mock();self.root.update()
  self.path=Path(self.tmp.name)/'card.png';Image.new('RGB',(500,400),'white').save(self.path);self.row=dict(path=str(self.path),name='Card',sha256=file_digest(self.path),reviewed_load=None,options=[],card_regions=[])
  self.app.case['imported_files']=[dict(path=str(self.path))];self.app.case['local_photo_results']={str(self.path):dict(sha256=self.row['sha256'])};self.rows=[self.row]
  self.patcher=patch('load_card_review.card_candidates',side_effect=lambda *a,**k:copy.deepcopy(self.rows));self.patcher.start();self.window=None
 def tearDown(self):
  if self.window and not self.window.closed:self.window.close()
  self.patcher.stop();self.root.destroy();self.tmp.cleanup();self.assertEqual(self.errors,[])
 def open_cards(self):
  from load_card_review import CardReviewWindow
  self.window=CardReviewWindow(self.app);self.root.update();return self.window
 def test_arriving_readings_update_suggestions_without_recreating_preview_or_assigning_trip(self):
  win=self.open_cards();preview=win.preview;self.rows[0].update(options=[42],stage_suggestion='quarter',stage_status='single_reader');win.refresh(preserve=True);self.root.update()
  self.assertEqual(win.vendor_number.get(),'42');self.assertEqual(win.number.get(),'');self.assertEqual(win.stage.get(),'Not Clear / Not Shown');self.assertIn('Quarter Full',win.status.cget('text'));self.assertIs(win.preview,preview)
  win.use_suggested_stage();self.assertEqual(win.stage.get(),'Quarter Full');self.assertNotIn('load_card_reviews',self.app.case);self.assertNotIn('photo_load_assignments',self.app.case)
 def test_background_updates_keep_each_manually_edited_field(self):
  win=self.open_cards();win.number.set('2');win.vendor_number.set('9');win.stage.set('Half Full');self.rows[0].update(options=[8],stage_suggestion='full',stage_status='single_reader');win.refresh(preserve=True);self.root.update()
  self.assertEqual((win.number.get(),win.vendor_number.get(),win.stage.get()),('2','9','Half Full'))
 def test_changed_source_does_not_keep_unconfirmed_inputs_from_old_photo(self):
  win=self.open_cards();win.number.set('2');win.vendor_number.set('9');win.stage.set('Half Full');Image.new('RGB',(500,400),'red').save(self.path);self.rows[0]['sha256']=file_digest(self.path);win.refresh(preserve=True);self.root.update();self.assertEqual((win.number.get(),win.vendor_number.get(),win.stage.get()),('','','Not Clear / Not Shown'))
 def test_last_confirmation_finishes_queue_and_reviewed_cards_remain_accessible(self):
  win=self.open_cards();win.number.set('1');win.vendor_number.set('2')
  def save(*a,**k):self.rows[0].update(reviewed_load=1,reviewed_vendor=2)
  with patch('load_card_review.confirm_card',side_effect=save):win.confirm()
  self.root.update();self.assertIsNone(win.selected());self.assertIn('All available cards are reviewed',win.status.cget('text'));self.assertIn('disabled',win.confirm_button.state());self.assertIsNone(win.preview)
  win.show_reviewed.set(True);win.refresh();self.root.update();self.assertEqual(win.number.get(),'1');self.assertIsNotNone(win.preview)
 def test_changed_source_cannot_use_stage_hint(self):
  self.rows[0].update(stage_suggestion='full',stage_status='single_reader');win=self.open_cards();Image.new('RGB',(500,400),'red').save(self.path)
  with patch('load_card_review.messagebox.showwarning') as warning:win.use_suggested_stage();self.assertTrue(warning.called)
  self.assertEqual(win.stage.get(),'Not Clear / Not Shown')
 def test_missing_photo_cannot_use_or_hide_a_card_suggestion(self):
  self.rows[0].update(stage_suggestion='full',stage_status='single_reader');win=self.open_cards();self.path.unlink()
  with patch('load_card_review.messagebox.showwarning') as warning:
   win.use_suggested_stage();win.dismiss();self.assertEqual(warning.call_count,2)
  self.assertEqual(win.stage.get(),'Not Clear / Not Shown');self.assertNotIn('load_card_dismissals',self.app.case)
 def test_cancelled_open_and_save_resume_current_case_processing(self):
  with patch('package_ui.filedialog.askopenfilename',return_value=''):self.app.open_case()
  self.app.start_photo_work.assert_called_once();self.app.start_photo_work.reset_mock()
  with patch('package_ui.filedialog.asksaveasfilename',return_value=''):self.app.save_project()
  self.app.start_photo_work.assert_called_once()
 def test_new_case_cancel_preserves_current_case_and_resumes_processing(self):
  import tkinter.ttk as ttk
  previous=self.app.case;self.app.new_case();self.root.update()
  def all_widgets(w):
   for child in w.winfo_children():yield child;yield from all_widgets(child)
  cancel=next(w for w in all_widgets(self.root) if isinstance(w,ttk.Button) and w.cget('text')=='Cancel');cancel.invoke();self.root.update();self.assertIs(self.app.case,previous);self.app.start_photo_work.assert_called_once()
 def test_failed_open_keeps_current_case_and_resumes_processing(self):
  previous=self.app.case
  with patch('package_ui.filedialog.askopenfilename',return_value=str(Path(self.tmp.name)/'broken.edcase')),patch('background_task.run_file_task',side_effect=ValueError('bad project')),patch('package_ui.messagebox.showerror'):self.app.open_case()
  self.assertIs(self.app.case,previous);self.app.start_photo_work.assert_called_once()
