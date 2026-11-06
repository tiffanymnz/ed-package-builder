"""Open the actual interface with an empty synthetic case; no vendor files."""
import json,sys,tempfile,traceback
from pathlib import Path

def run(report_path):
    result=dict(status='FAIL',app_frozen=bool(getattr(sys,'frozen',False)),synthetic_only=True);root=None
    try:
        import tkinter as tk
        from package_ui import PackageApp
        from ed_app import make_case
        with tempfile.TemporaryDirectory(prefix='ed-ui-smoke-') as folder:
            root=tk.Tk();errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
            app=PackageApp(root);app.start_photo_work=lambda:None
            app.case=make_case('UI-SMOKE','','Synthetic Test Vendor',1,35);app.case_dir=Path(folder)
            app.refresh();root.geometry('1000x740');root.update();titles=[]
            def capture(name,window):
                if sys.platform!='win32':return
                try:
                    from PIL import ImageGrab
                    window.update();directory=Path(report_path).parent/'ed-ui-proof';directory.mkdir(exist_ok=True)
                    box=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())
                    ImageGrab.grab(bbox=box,all_screens=True).save(directory/(name+'.png'))
                    result.setdefault('synthetic_screenshots',[]).append(name+'.png')
                except Exception as exc:result.setdefault('screenshot_warnings',[]).append(type(exc).__name__)

            for step,expected in enumerate(('Import Files','Review Loads','Review Costs','Create Package')):
                app.go(step);root.update();title=app.page_title.get();titles.append(title)
                assert title==expected,'Incorrect workflow page'
                capture('step-'+str(step+1),root)
                assert app.next_button.winfo_ismapped(),'Next action is hidden'
                assert app.next_button.winfo_rooty()+app.next_button.winfo_height()<=root.winfo_rooty()+root.winfo_height(),'Next action extends below window'
                assert app.next_button.winfo_rootx()+app.next_button.winfo_width()<=root.winfo_rootx()+root.winfo_width(),'Next action extends outside window'
            from PIL import Image
            from photo_flow import PhotoFlowWindow
            import time
            for index in range(24):
                photo=Path(folder)/f'view-{index}.png';Image.new('RGB',(320,240),(index*9,80,130)).save(photo)
                app.case['imported_files'].append(dict(path=str(photo),name=photo.name))
            window=PhotoFlowWindow(app);deadline=time.monotonic()+8
            while len(window.rows)!=24 and time.monotonic()<deadline:root.update();time.sleep(.02)
            assert len(window.rows)==24,'Photo review did not finish preparing synthetic views'
            densities=[]
            for size in ('6','12','24'):
                window.page_size.set(size);window.reset_page();root.update()
                assert len(window.images)==int(size),'Wrong number of review previews'
                densities.append(int(size));capture('review-'+size,window.win)
            assert window.apply_button.winfo_rooty()+window.apply_button.winfo_height()<=window.win.winfo_rooty()+window.win.winfo_height(),'Review action extends below the window'
            window.close();root.update()
            result['photo_densities']=densities
            assert not errors,'Interface callback failed: '+str(errors)
            result.update(status='PASS',pages=titles,width=root.winfo_width(),height=root.winfo_height())
            root.destroy();root=None
    except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:
        if root is not None:
            try:root.destroy()
            except Exception:pass
    Path(report_path).parent.mkdir(parents=True,exist_ok=True);Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASS' else 1
