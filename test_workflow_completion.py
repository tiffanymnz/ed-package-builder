import tempfile
from pathlib import Path
import unittest
import tkinter as tk
from PIL import Image
from accuracy_audit import score
from workflow_status import package_inventory
from photo_inspector import inspect_photos,PhotoPane

class AuditTests(unittest.TestCase):
    def test_wrong_and_unresolved_are_separate(self):
        labels=[dict(id=str(i),case='unseen',load=2,purpose='half',source_sha256='hash',split='unseen') for i in range(3)]
        guesses=[dict(r,load=n) for r,n in zip(labels,[2,1,None])]
        value=score(labels,guesses)['overall']['load']
        self.assertEqual([value[k] for k in ('correct','wrong','unresolved')],[1,1,1]);self.assertEqual(value['precision'],.5)
    def test_rejects_leakage_and_source_changes(self):
        row=dict(id='a',case='training',load=2,purpose='half',source_sha256='hash',split='unseen')
        with self.assertRaises(ValueError):score([row],[row],['training'])
        with self.assertRaises(ValueError):score([row],[dict(row,source_sha256='other')])
    def test_missing_predictions_cannot_disappear_from_denominator(self):
        row=dict(id='a',case='test',load=2,purpose='half',source_sha256='hash',split='unseen')
        with self.assertRaises(ValueError):score([row],[])
    def test_inventory_does_not_call_missing_sources_attached(self):
        case=dict(loads=[dict(photos={'height':'not-there'})],package_documents=[],before_photos=['missing'])
        rows=package_inventory(case);load=next(r for r in rows if r['label']=='Load 1')
        self.assertEqual(load['slot'],'height');self.assertIn('Select',next(r for r in rows if r['label']=='Before Removal')['detail'])

class InspectorTests(unittest.TestCase):
    def test_compare_zoom_rotate_preserves_original_bytes(self):
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        try:
            with tempfile.TemporaryDirectory() as folder:
                files=[]
                for i in range(2):
                    path=Path(folder)/f'{i}.jpg';Image.new('RGB',(900,600),'blue').save(path);files.append(str(path))
                original=[Path(p).read_bytes() for p in files]
                win=inspect_photos(root,files);root.update()
                pane=next(w for w in win.winfo_children() if isinstance(w, __import__('tkinter').ttk.Panedwindow))
                frames=[pane.nametowidget(p) for p in pane.panes()];self.assertEqual(len(frames),2)
                for frame in frames:
                    before=frame.scale;frame.zoom(1.25);self.assertGreater(frame.scale,before);frame.rotate();self.assertEqual(frame.rotation,90);frame.fit()
                self.assertEqual(original,[Path(p).read_bytes() for p in files]);win.destroy()
        finally:root.destroy()

class SourceExportTests(unittest.TestCase):
    def test_export_audit_tracks_every_template_slot(self):
        from test_cor_package import fixture
        from cor_package import assemble
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);case=fixture(folder);report=assemble(case,folder/'output.pdf')
            slots=[r for r in report['sources'] if r.get('section')=='Load 1']
            self.assertEqual(len(slots),13);self.assertTrue(all(len(r['sha256'])==64 for r in report['sources']))
    def test_source_mutation_during_export_keeps_previous_pdf(self):
        from unittest.mock import patch
        from test_cor_package import fixture
        import cor_package
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);case=fixture(folder);target=folder/'output.pdf';target.write_bytes(b'previous')
            original=cor_package.property_photo_pages
            def change(*args):
                result=original(*args);Path(case['before_photos'][0]).write_bytes(b'changed');return result
            # Mutate after the final image insert, so source hash verification catches it.
            with patch.object(cor_package,'property_photo_pages',side_effect=lambda doc,paths,title:change(doc,paths,title) if title=='After Photos' else original(doc,paths,title)):
                with self.assertRaisesRegex(ValueError,'source changed'):cor_package.assemble(case,target)
            self.assertEqual(target.read_bytes(),b'previous')
    def test_cancelled_save_preserves_existing_project_and_cleans_partial(self):
        import threading
        from ed_app import make_case
        from portable_project import export_project
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);root=folder/'case';root.mkdir();(root/'a.txt').write_text('data')
            target=folder/'saved.edcase';target.write_bytes(b'previous');cancel=threading.Event()
            def progress(message):
                if message.startswith('Saving File'):cancel.set()
            with self.assertRaises(InterruptedError):export_project(make_case('CASE','','Vendor',1,35),root,target,cancel=cancel,progress=progress)
            self.assertEqual(target.read_bytes(),b'previous');self.assertFalse(list(folder.glob('.ed-project-*')))

class FileTaskTests(unittest.TestCase):
    def test_ui_remains_responsive_while_worker_runs(self):
        import time
        from background_task import run_file_task
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        ticks=[]
        try:
            root.after(10,lambda:ticks.append(True))
            def worker(cancel,progress):
                time.sleep(.12);progress('Checking...');return 42
            self.assertEqual(run_file_task(root,'Test Operation',worker),42);self.assertTrue(ticks)
        finally:root.destroy()
