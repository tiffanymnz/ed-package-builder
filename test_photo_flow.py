import copy
from pathlib import Path
import tempfile,time,threading
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image
from calculator_evidence import file_digest
from photo_flow import build_photo_rows,PhotoFlowWindow,BackgroundPhotoWork
from review_assist import confirm_load_membership

class PhotoFlowDataTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
  self.case=dict(case_number='FLOW',loads=[{'photos':{}},{'photos':{}}],imported_files=[],photo_text_cache={})
 def tearDown(self):self.temp.cleanup()
 def photo(self,name,text='',stamp=None):
  p=self.folder/name;im=Image.new('RGB',(500,350),'blue');exif=Image.Exif()
  if stamp:exif[36867]=stamp
  im.save(p,exif=exif);self.case['imported_files'].append(dict(path=str(p),name=name));self.case['photo_text_cache'][str(p)]=dict(sha256=file_digest(p),text=text)
  return str(p)
 def test_time_orders_only_and_does_not_assign_same_container_loads(self):
  late=self.photo('before_load1.jpg',stamp='2026:08:24 14:00:00');early=self.photo('after_load9.jpg',stamp='2026:08:24 09:00:00')
  before=copy.deepcopy(self.case);rows,_=build_photo_rows(self.case)
  self.assertEqual(sorted(rows,key=lambda r:r['sort_key'])[0]['path'],early)
  self.assertTrue(all(r['load'] is None and r['stage']=='review' for r in rows));self.assertEqual(self.case,before)
 def test_date_only_keeps_import_order_without_inventing_time(self):
  a=self.photo('b.jpg','2026-08-24');b=self.photo('a.jpg','2026-08-24');rows,_=build_photo_rows(self.case)
  self.assertEqual([r['path'] for r in sorted(rows,key=lambda r:r['sort_key'])],[a,b]);self.assertTrue(all('Date Only' in r['timing'] for r in rows))
 def test_conflicting_camera_and_visible_dates_are_not_used_for_order(self):
  self.photo('p.jpg','2026-08-25 12:00',stamp='2026:08:24 09:00:00');rows,_=build_photo_rows(self.case)
  self.assertEqual(rows[0]['timing'],'Conflicting Dates');self.assertEqual(rows[0]['sort_key'][0],'9999')
 def test_stale_text_does_not_create_timing_clue(self):
  p=self.photo('p.jpg','2026-08-24 12:00');self.case['photo_text_cache'][p]['sha256']='old';rows,_=build_photo_rows(self.case)
  self.assertEqual(rows[0]['timing'],'Date Not Available')
 def test_unchanged_source_index_reuses_validated_bytes(self):
  self.photo('p.jpg','2026-08-24');rows,_=build_photo_rows(self.case)
  with patch('photo_flow.checked_rows',side_effect=AssertionError('Unchanged source rehashed')):
   again,_=build_photo_rows(self.case,rows)
  self.assertEqual(again[0]['sha256'],rows[0]['sha256'])
 def test_same_container_views_can_be_reviewed_as_different_loads(self):
  a=self.photo('a.jpg');b=self.photo('b.jpg');rows,checked=build_photo_rows(self.case)
  for r in rows:checked.setdefault(r['path'],{})['sha256']=r['sha256']
  confirm_load_membership(self.case,[a],1,checked);confirm_load_membership(self.case,[b],2,checked)
  rows,_=build_photo_rows(self.case);self.assertEqual([r['load'] for r in rows],[1,2]);self.assertEqual(self.case['loads'],[{'photos':{}},{'photos':{}}])
 def test_changed_batch_source_leaves_all_loads_unassigned(self):
  a=self.photo('a.jpg');b=self.photo('b.jpg');rows,checked=build_photo_rows(self.case)
  for r in rows:checked.setdefault(r['path'],{})['sha256']=r['sha256']
  Path(b).write_bytes(b'changed')
  with self.assertRaises(ValueError):confirm_load_membership(self.case,[a,b],1,checked)
  self.assertNotIn('photo_load_assignments',self.case)

class PhotoFlowUiTests(unittest.TestCase):
 def setUp(self):
  try:self.root=tk.Tk()
  except tk.TclError as e:self.skipTest(str(e))
  warning=patch('tkinter.messagebox.showwarning',side_effect=AssertionError('Unexpected warning dialog'));warning.start();self.addCleanup(warning.stop)
  from package_ui import PackageApp
  from ed_app import make_case
  self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.app=PackageApp(self.root);self.app.case=make_case('FLOW','','Vendor',2,35);self.app.case_dir=self.folder;self.errors=[];self.root.report_callback_exception=lambda *a:self.errors.append(a)
  for i in range(8):
   p=self.folder/f'photo-{i}.jpg';Image.new('RGB',(800,500),(i*20,100,130)).save(p);self.app.case['imported_files'].append(dict(path=str(p),name=p.name))
  self.app.refresh();self.root.update();self.start=patch.object(self.app,'start_photo_work');self.start.start();self.window=PhotoFlowWindow(self.app)
  self.wait(lambda:len(self.window.rows)==8)
 def wait(self,condition,seconds=5):
  deadline=time.monotonic()+seconds
  while not condition() and time.monotonic()<deadline:self.root.update();time.sleep(.01)
  self.assertTrue(condition());self.root.update()
 def tearDown(self):
  if not self.window.closed:self.window.close()
  service=self.app._background_photos
  if service:
   service.close();deadline=time.monotonic()+5
   while service.running and time.monotonic()<deadline:time.sleep(.01)
  self.start.stop();self.root.destroy();self.temp.cleanup()
 def test_density_change_keeps_selection_and_shows_all_available_previews(self):
  self.window.select_page();selected=set(self.window.selected)
  for size in ('12','24','6'):
   self.window.page_size.set(size);self.window.reset_page();self.root.update()
   self.assertEqual(self.window.selected,selected)
   self.assertEqual(len(self.window.images),min(int(size),len(self.window.rows)))
  self.assertEqual(self.errors,[])
 def test_six_large_previews_and_batch_assignment(self):
  self.assertEqual(len(self.window.images),6);self.assertFalse(any(v.get() for v in self.window.check_vars))
  self.window.select_page();self.assertTrue(all(v.get() for v in self.window.check_vars));self.assertEqual(str(self.window.apply_button.cget('state')),'disabled')
  self.window.target.set('Load 2');self.assertEqual(str(self.window.apply_button.cget('state')),'normal');self.window.apply()
  self.assertEqual(len(self.app.case['photo_load_assignments']),6);self.assertEqual(self.app.case['loads'][1]['photos'],{});self.assertEqual(self.errors,[])
 def test_automatic_photo_group_filter_does_not_invent_a_load(self):
  for r in self.window.rows[:2]:r['proposal']=dict(group_label='Photo Group 1',load=None,status='unlabelled_group')
  self.window.update_choices();self.assertIn('Photo Group 1',self.window.load_box.cget('values'))
  self.window.load_filter.set('Photo Group 1');self.window.filter_load()
  self.assertEqual(len(self.window.filtered()),2);self.assertEqual(self.window.target.get(),'Choose a Load or Stage')
  self.assertFalse(self.window.selected);self.assertNotIn('photo_load_assignments',self.app.case)
 def test_photo_group_next_step_requires_an_actual_load_and_uses_the_chosen_one(self):
  self.window.rows[0]['proposal']=dict(group_label='Photo Group 1',load=None,status='unlabelled_group')
  self.window.update_choices();self.window.load_filter.set('Photo Group 1');self.window.filter_load()
  with patch.object(self.app,'template_photo_review') as next_step:
   self.window.next_step();next_step.assert_not_called();self.assertFalse(self.window.closed)
   self.window.target.set('Load 2');self.window.next_step();next_step.assert_called_once()
  self.assertEqual(self.app.e_load.get(),'2')
 def test_background_update_preserves_visible_selection(self):
  self.window.select_page();visible=[r['path'] for r in self.window.visible];self.window.mark_dirty()
  self.wait(lambda:not self.window.loading and not self.window.dirty)
  self.assertEqual([r['path'] for r in self.window.visible],visible);self.assertEqual(len(self.window.selected),6)
 def test_batch_type_correction_does_not_assign_load_or_stage(self):
  self.window.select_page();self.window.change_category('measurement')
  self.wait(lambda:not self.window.loading and not self.window.dirty)
  self.assertEqual(len(self.app.case['photo_category_examples']),6)
  self.assertNotIn('photo_load_assignments',self.app.case);self.assertEqual(self.app.case['before_photos'],[])
 def test_next_step_uses_chosen_load(self):
  self.window.load_filter.set('Load 2')
  with patch.object(self.app,'template_photo_review') as next_step:self.window.next_step()
  next_step.assert_called_once();self.assertEqual(self.app.e_load.get(),'2');self.assertTrue(self.window.closed)
 def test_suggested_load_filter_does_not_preselect_or_assign_photos(self):
  from load_text_runtime import MODEL_DIGEST
  from load_identity import VERSION as LOAD_VERSION
  path=self.app.case['imported_files'][0]['path'];self.app.case['load_identity_cache']={path:dict(sha256=file_digest(path),model_digest=MODEL_DIGEST,version=LOAD_VERSION,load=2,status='corroborated')}
  self.window.mark_dirty();self.wait(lambda:any(r.get('proposal',{}).get('load')==2 for r in self.window.rows))
  self.window.load_filter.set('Suggested Load 2');self.window.filter_load()
  self.assertEqual(self.window.target.get(),'Load 2');self.assertEqual(len(self.window.filtered()),1);self.assertFalse(self.window.selected)
  self.assertNotIn('photo_load_assignments',self.app.case)
  self.window.load_filter.set('Load Clues to Review');self.window.filter_load();self.assertEqual(len(self.window.filtered()),1)
 def test_save_open_actions_wait_once_for_current_background_photo(self):
  from types import SimpleNamespace
  service=SimpleNamespace(running=True,cancel=threading.Event(),case=self.app.case,close=lambda:None)
  self.app._background_photos=service
  action=unittest.mock.Mock()
  self.assertTrue(self.app.finish_photo_work(action));self.assertTrue(self.app.finish_photo_work(action));self.assertTrue(service.cancel.is_set())
  service.running=False;self.wait(lambda:action.call_count==1)
  self.assertFalse(self.app._deferred_project_save)
 def test_smaller_screen_keeps_batch_and_next_controls_visible(self):
  self.window.win.geometry('900x650');self.root.update();self.window.render();self.root.update()
  def walk(w):
   for c in w.winfo_children():yield c;yield from walk(c)
  buttons=[b for b in walk(self.window.win) if isinstance(b,tk.ttk.Button) and b.cget('text') in ('Apply to Selected','Next: Fill Template')]
  self.assertEqual(len(buttons),2)
  for b in buttons:self.assertLessEqual(b.winfo_rooty()+b.winfo_height(),self.window.win.winfo_rooty()+self.window.win.winfo_height())
  self.assertEqual(len(self.window.images),6);self.assertEqual(self.errors,[])
 def test_automatic_worker_reads_text_and_publishes_results_without_assignments(self):
  from local_photo_sorter import MODEL_DIGEST,VERSION
  def fake_batch(records,model,cache,cancel,on_result):
   for i,r in enumerate(records):on_result(r['path'],dict(sha256=file_digest(r['path']),model_digest=MODEL_DIGEST,prompt_version=VERSION,prediction={'category':'container_photos'}),i+1,len(records),0,0)
   return dict(cancelled=False)
  self.window.close()
  self.app.go(2)
  with patch('photo_flow.RUNTIME.ready',return_value=True),patch('photo_flow.batch',side_effect=fake_batch),patch('package_ui.read_image',return_value=('2026-08-24 12:00','')) as reader,patch.object(self.app,'draw_finance') as redraw:
   service=BackgroundPhotoWork(self.app);self.app._background_photos=service
   self.wait(lambda:len(self.app.case.get('photo_text_cache',{}))==8,seconds=7)
   self.assertEqual(reader.call_count,8);self.assertEqual(len(self.app.case['local_photo_results']),8)
   self.assertNotIn('photo_load_assignments',self.app.case);self.assertEqual(self.app.case['loads'][0]['photos'],{})
   redraw.assert_not_called()
   service.close()
