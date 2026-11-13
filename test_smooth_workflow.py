"""Regression checks for cancellable, responsive package and project operations."""
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch

class CancelledFileOperations(unittest.TestCase):
    def test_load_summary_points_to_repeated_stage_evidence(self):
        from test_cor_package import fixture
        from workflow_status import package_inventory
        with tempfile.TemporaryDirectory() as folder:
            case=fixture(Path(folder));load=case['loads'][1];load['photos']['half']=load['photos']['quarter']
            row=next(r for r in package_inventory(case) if r.get('load')==2)
            self.assertEqual(row['detail'],'Review Repeated Loading Photos');self.assertIn(row['slot'],('quarter','half'))
    def test_description_rechecks_invoice_even_with_current_confirmation(self):
        from test_cor_package import fixture
        from cor_package import description,financial_fingerprint
        with tempfile.TemporaryDirectory() as folder:
            case=fixture(Path(folder));case['invoice_quantity_cyd']='40.19';case['financial_confirmation_hash']=financial_fingerprint(case)
            with self.assertRaisesRegex(ValueError,'Invoice cubic yards differ'):description(case)

    def test_cancel_export_mid_photos_preserves_all_previous_outputs(self):
        from test_cor_package import fixture
        from cor_package import assemble
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);case=fixture(root);out=root/'package.pdf'
            previous={out:b'previous pdf',root/'Package_Review.json':b'previous report',root/'COR_Request_Description.txt':b'previous description'}
            for p,data in previous.items():p.write_bytes(data)
            case['before_photos']*=20
            cancel=threading.Event();messages=[]
            def progress(message):
                messages.append(message)
                if message.startswith('Adding before photos:'):cancel.set()
            with self.assertRaises(InterruptedError):assemble(case,out,cancel=cancel,progress=progress)
            self.assertTrue(any(m.startswith('Adding before photos:') for m in messages))
            for p,data in previous.items():self.assertEqual(p.read_bytes(),data)
            self.assertFalse(list(root.glob('.cor-build-*')))

    def test_cancel_import_preserves_saved_archive(self):
        from test_cor_package import fixture
        from portable_project import export_project,import_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();case=fixture(source)
            saved=root/'case.edcase';export_project(case,source,saved);original=saved.read_bytes()
            cancel=threading.Event()
            def progress(message):
                if message.startswith('Opening saved source'):cancel.set()
            with self.assertRaises(InterruptedError):import_project(saved,root/'restored',cancel=cancel,progress=progress)
            self.assertEqual(saved.read_bytes(),original)
            self.assertFalse((root/'restored'/'case.json').exists())

class ResponsiveExport(unittest.TestCase):
    def test_load_summary_opens_the_selected_load(self):
        import tkinter as tk
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        from package_ui import PackageApp
        from test_cor_package import fixture
        with tempfile.TemporaryDirectory() as folder:
            app=PackageApp(root);app.start_photo_work=lambda:None;app.case_dir=Path(folder);app.case=fixture(app.case_dir);app.refresh();root.update()
            app.load_progress.selection_set('2')
            def widgets(parent):
                for child in parent.winfo_children():yield child;yield from widgets(child)
            button=next(w for w in widgets(root) if w.winfo_class()=='TButton' and w.cget('text')=='Review Selected Load')
            with patch.object(app,'template_photo_review') as review:button.invoke();review.assert_called_once()
            self.assertEqual(app.e_load.get(),'2')

    def test_saved_package_screen_opens_the_actual_files(self):
        import tkinter as tk
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        from package_ui import PackageApp
        app=PackageApp(root)
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'chosen.pdf'
            app.export_result(dict(status='Complete',pages=12,issues=[]),pdf);root.update()
            def widgets(parent):
                for child in parent.winfo_children():yield child;yield from widgets(child)
            buttons={w.cget('text'):w for w in widgets(root) if w.winfo_class()=='TButton'}
            with patch.object(app,'open_original') as opened:buttons['Open PDF'].invoke();opened.assert_called_once_with(pdf)
            buttons['Done'].invoke()
            app.export_result(dict(status='Items Missing',pages=9,issues=['Missing photo']),pdf);root.update()
            buttons={w.cget('text'):w for w in widgets(root) if w.winfo_class()=='TButton'}
            with patch.object(app,'go') as go:buttons['Review Remaining Items'].invoke();go.assert_called_once_with(3)

    def test_actual_export_processes_ui_events_and_reports_progress(self):
        import tkinter as tk,time
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        from package_ui import PackageApp
        from test_cor_package import fixture
        import package_ui
        with tempfile.TemporaryDirectory() as folder:
            app=PackageApp(root);app.start_photo_work=lambda:None
            app.case_dir=Path(folder);app.case=fixture(app.case_dir);app.refresh();root.update()
            ticks=[];snapshot=[];original=package_ui.assemble
            def assemble(case,*args,**kwargs):
                snapshot.append(case);time.sleep(.15);return original(case,*args,**kwargs)
            root.after(20,lambda:ticks.append(True))
            with patch.object(package_ui,'assemble',side_effect=assemble),patch('tkinter.messagebox.askyesno',return_value=True),patch('tkinter.messagebox.showinfo'),patch('tkinter.messagebox.showerror') as error,patch.object(app,'open_output'):
                app.generate()
            error.assert_not_called();self.assertTrue(ticks)
            self.assertIsNot(snapshot[0],app.case);self.assertFalse(app._file_task_running)
            self.assertTrue((app.case_dir/'output'/'TEST-001_COR_PACKAGE_DRAFT.pdf').is_file())

    def test_file_operation_prevents_case_switch_and_duplicate_export(self):
        from package_ui import PackageApp
        app=object.__new__(PackageApp);app._file_task_running=True
        self.assertFalse(app.prepare_leave());self.assertFalse(app.save_project())
        self.assertIsNone(app.new_case());self.assertIsNone(app.open_case());self.assertIsNone(app.generate())

class ExportPhotoQuality(unittest.TestCase):
    def test_imported_pdf_keeps_referenced_transparency_group(self):
        import fitz
        from cor_package import append_pdf_page
        with fitz.open() as source,fitz.open() as target:
            page=source.new_page();page.insert_text((30,40),'Original invoice')
            page.draw_rect(fitz.Rect(40,60,200,160),fill=(.2,.5,.8),fill_opacity=.5)
            group=source.get_new_xref();source.update_object(group,'<</Type/Group/S/Transparency/CS/DeviceRGB/I true/K false>>')
            source.xref_set_key(page.xref,'Group',f'{group} 0 R')
            with fitz.open(stream=source.tobytes(),filetype='pdf') as original:
                expected=original[0].get_pixmap().samples
                append_pdf_page(target,original,0)
                with fitz.open(stream=target.tobytes(),filetype='pdf') as reopened:
                    self.assertNotEqual(reopened.xref_get_key(reopened[0].xref,'Group')[0],'null')
                    self.assertEqual(reopened[0].get_pixmap().samples,expected)
                    self.assertEqual(reopened[0].get_text(),original[0].get_text())

    def test_ordinary_jpeg_keeps_original_compressed_photo(self):
        import fitz
        from PIL import Image
        from cor_package import insert_picture
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.jpg';Image.new('RGB',(900,600),'#295c7e').save(path,quality=94)
            with fitz.open() as doc:
                page=doc.new_page();insert_picture(page,fitz.Rect(30,40,500,500),path)
                image=doc.extract_image(page.get_images()[0][0])
                self.assertEqual(image['image'],path.read_bytes())

    def test_exif_rotated_photo_is_upright_in_the_pdf(self):
        import fitz
        from PIL import Image
        from cor_package import insert_picture
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rotated.jpg';im=Image.new('RGB',(900,600),'#295c7e');exif=im.getexif();exif[274]=6;im.save(path,exif=exif)
            with fitz.open() as doc:
                page=doc.new_page();insert_picture(page,fitz.Rect(30,40,500,700),path)
                image=doc.extract_image(page.get_images()[0][0]);self.assertEqual((image['width'],image['height']),(600,900))

class MeasurementControlIntegration(unittest.TestCase):
    def test_control_only_withholds_measurements_and_never_assigns_evidence(self):
        import numpy as np
        from small_vision_runtime import SmallVisionRuntime
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            runtime=SmallVisionRuntime(Path(folder));runtime.session=Mock();runtime.session.run.return_value=[np.ones((1,512),np.float32)]
            try:
                for category,expected in [('measurement','unclear'),('property_photos','property_photos')]:
                    with patch.object(runtime,'start'),patch('small_vision_runtime.prepare_pixels',return_value=np.zeros((1,3,224,224),np.float32)),patch('photo_category_head.predict_category',return_value=dict(category=category,category_score=.95,head_version='test')),patch('photo_category_head.image_has_content',return_value=True),patch('measurement_controls.supports_measurement',return_value=False):
                        result=runtime.classify('synthetic.jpg')
                    self.assertEqual(result['category'],expected);self.assertIsNone(result['load_number']);self.assertFalse(result['verified'])
            finally:runtime.stop()
