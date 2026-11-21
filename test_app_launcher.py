import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app_launcher import launch
class LauncherTests(unittest.TestCase):
 def test_startup_exception_has_readable_error_and_log(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'ED_STARTUP_LOG_DIR':folder}),patch('tkinter.messagebox.showerror') as dialog:
   def broken():raise RuntimeError('synthetic startup error')
   self.assertEqual(launch(broken),1);self.assertIn('synthetic startup error',(Path(folder)/'startup-error.txt').read_text());dialog.assert_called_once()
 def test_success_preserves_exit_status(self):
  self.assertEqual(launch(lambda:None),0);self.assertEqual(launch(lambda:3),3)
 def test_windowed_streams_do_not_break_startup(self):
  files=[]
  try:
   with patch.object(sys,'stdout',None),patch.object(sys,'stderr',None):
    def check():
     self.assertIsNotNone(sys.stdout);self.assertIsNotNone(sys.stderr);files.extend([sys.stdout,sys.stderr])
    self.assertEqual(launch(check),0)
  finally:
   for f in files:f.close()

 def test_automated_failure_does_not_wait_for_a_dialog(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'ED_STARTUP_LOG_DIR':folder}),patch.object(sys,'argv',['app.exe','--smoke-test','report.json']),patch('tkinter.messagebox.showerror') as dialog:
   def broken():raise RuntimeError('synthetic automated failure')
   self.assertEqual(launch(broken),1);dialog.assert_not_called();self.assertTrue((Path(folder)/'startup-error.txt').exists())
