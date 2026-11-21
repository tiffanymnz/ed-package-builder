"""Faster selection, explicit batch scope and clearer first-run actions."""
import unittest
from unittest.mock import patch
import test_photo_flow as flow_fixture

class SelectionEfficiencyTests(unittest.TestCase):
 setUp=flow_fixture.PhotoFlowUiTests.setUp
 tearDown=flow_fixture.PhotoFlowUiTests.tearDown
 wait=flow_fixture.PhotoFlowUiTests.wait
 def test_selection_updates_without_image_reads_or_grid_rebuilds(self):
  window=self.window;window.win.update();images=list(window.images);cards=list(window.cards.winfo_children());path=window.visible[0]['path']
  with patch('photo_flow.Image.open',side_effect=AssertionError('Selection decoded a photo')),patch('photo_flow.file_digest',side_effect=AssertionError('Selection rehashed a photo')):
   window.toggle(path);self.assertTrue(window.check_vars[0].get());window.select_page();self.assertTrue(all(v.get() for v in window.check_vars));window.clear_selection();self.assertFalse(any(v.get() for v in window.check_vars))
  self.assertEqual(window.images,images);self.assertEqual(window.cards.winfo_children(),cards)
 def test_selection_on_other_pages_remains_available(self):
  w=self.window;first=w.visible[0]['path'];w.toggle(first);w.move(1);w.select_page();self.assertIn(first,w.selected);self.assertEqual(len(w.selected),3);w.move(-1);self.assertTrue(w.check_vars[0].get())
 def test_outside_filter_batch_requires_explicit_confirmation(self):
  w=self.window;w.toggle(w.visible[0]['path']);w.category.set('measurement');w.reset_page();self.assertIn('Outside Filter',w.selection.cget('text'));w.target.set('Load 1')
  with patch('photo_flow.messagebox.askyesno',return_value=False) as ask:w.apply();ask.assert_called_once()
  self.assertNotIn('photo_load_assignments',self.app.case);self.assertEqual(len(w.selected),1)
 def test_changed_source_still_fails_assignment_after_fast_selection(self):
  from pathlib import Path
  w=self.window;path=w.visible[0]['path'];w.toggle(path);w.target.set('Load 1');Path(path).write_bytes(b'changed')
  with patch('photo_flow.messagebox.showwarning') as warning:w.apply();warning.assert_called_once()
  self.assertNotIn('photo_load_assignments',self.app.case)

class PlainLanguageTests(unittest.TestCase):
 def test_measurement_messages_use_visible_field_names(self):
  from ui_text import readable_issue
  self.assertEqual(readable_issue('Load 1 measurement: length_ft is not a number: '),'Load 1 measurement: Length (ft) needs a valid number.')
  self.assertIn('Wall Height (ft)',readable_issue('side_height_ft must be positive'))
 def test_no_case_actions_are_disabled_then_restored(self):
  import tkinter as tk,tempfile
  from pathlib import Path
  from package_ui import PackageApp
  from ed_app import make_case
  root=tk.Tk()
  try:
   app=PackageApp(root);root.update()
   self.assertTrue(all('disabled' in c.state() for c in (app.next_button,app.project_save_button,app.output_button)))
   with tempfile.TemporaryDirectory() as folder:
    app.case=make_case('TEST','','Vendor',1,35);app.case_dir=Path(folder);app.refresh();app.go(0);root.update()
    self.assertTrue(all('disabled' not in c.state() for c in (app.next_button,app.project_save_button,app.output_button)))
  finally:root.destroy()
