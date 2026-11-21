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
            from ui_windows import fit_window,work_area
            fit_window(root,root,(1000,740),(900,600));root.update();titles=[]
            def capture(name,window):
                if sys.platform!='win32':return
                try:
                    from PIL import ImageGrab
                    window.update();directory=Path(report_path).parent/'ed-ui-proof';directory.mkdir(exist_ok=True)
                    box=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())
                    ImageGrab.grab(bbox=box,all_screens=True).save(directory/(name+'.png'))
                    result.setdefault('synthetic_screenshots',[]).append(name+'.png')
                except Exception as exc:result.setdefault('screenshot_warnings',[]).append(type(exc).__name__)

            capture('first-run',root)
            app.new_case();root.update()
            new=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='New Case')
            def initial_widgets(parent):
                for w in parent.winfo_children():yield w;yield from initial_widgets(w)
            create=next(w for w in initial_widgets(new) if w.winfo_class()=='TButton' and w.cget('text')=='Create Case')
            assert create.winfo_ismapped() and create.winfo_rooty()+create.winfo_height()<=new.winfo_rooty()+new.winfo_height(),'New Case action is hidden'
            capture('new-case',new)
            next(w for w in initial_widgets(new) if w.winfo_class()=='TButton' and w.cget('text')=='Cancel').invoke();root.update()
            app.case=make_case('UI-SMOKE','','Synthetic Test Vendor',1,35);app.case_dir=Path(folder);app.refresh();root.update()
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
                assert all(im.width()>=80 and im.height()>=60 for im in window.images),'Photo previews are too small to inspect'
                assert window.undo_button.winfo_ismapped(),'Batch undo action is hidden'
                densities.append(int(size));capture('review-'+size,window.win)
            images=list(window.images);cards=list(window.cards.winfo_children())
            window.toggle(window.visible[0]['path']);window.select_page();root.update()
            assert len(window.selected)==24 and all(v.get() for v in window.check_vars),'Fast selection lost checked photos'
            assert window.images==images and window.cards.winfo_children()==cards,'Selection rebuilt the photo previews'
            window.clear_selection();root.update()
            assert not window.selected and not any(v.get() for v in window.check_vars),'Clear selection did not update the controls'
            result['selection_checks']=['previews_reused','page_selection','clear_selection']
            assert window.apply_button.winfo_rooty()+window.apply_button.winfo_height()<=window.win.winfo_rooty()+window.win.winfo_height(),'Review action extends below the window'
            left,top,right,bottom=work_area(root)
            assert window.apply_button.winfo_rooty()+window.apply_button.winfo_height()<=bottom-4,'Photo review action is obscured by the taskbar'
            assert window.apply_button.winfo_rootx()+window.apply_button.winfo_width()<=right,'Photo review action extends beyond the monitor'
            window.close();root.update()
            # Exercise the real card-review queue and live result refresh in
            # the packaged interface, using only synthetic sources and clues.
            from calculator_evidence import file_digest
            from local_photo_sorter import VERSION as PHOTO_VERSION,MODEL_DIGEST as PHOTO_MODEL
            from card_regions import VERSION as DETECTOR_VERSION
            from load_identity import VERSION as READER_VERSION
            from load_text_runtime import MODEL_DIGEST as READER_MODEL
            from load_card_review import CardReviewWindow
            path=app.case['imported_files'][0]['path'];sha=file_digest(path)
            app.case.setdefault('local_photo_results',{})[path]=dict(sha256=sha,prompt_version=PHOTO_VERSION,model_digest=PHOTO_MODEL,card_detector_version=DETECTOR_VERSION,card_detected=True,card_regions=[dict(box=[.2,.2,.7,.7])])
            cards=CardReviewWindow(app);root.update();preview=cards.preview
            assert cards.selected() and cards.number.get()=='','Card review needs an explicit package load'
            app.case.setdefault('load_identity_cache',{})[path]=dict(sha256=sha,version=READER_VERSION,model_digest=READER_MODEL,status='single_reader',options=[2],stage_reading=dict(stage='full',options=['full'],status='single_reader'))
            cards.refresh(preserve=True);root.update()
            assert cards.preview is preview and cards.vendor_number.get()=='2','Arriving card reading was not shown'
            assert cards.stage.get()=='Not Clear / Not Shown' and 'Possible Stage: Full' in cards.status.cget('text'),'Stage suggestion must be visible and unconfirmed'
            cards.use_suggested_stage();cards.number.set('1');cards.vendor_number.set('9')
            app.case['load_identity_cache'][path]['options']=[3];cards.refresh(preserve=True);root.update()
            assert cards.vendor_number.get()=='9' and cards.number.get()=='1' and cards.stage.get()=='Full','Live update overwrote a manual choice'
            assert cards.confirm_button.winfo_rooty()+cards.confirm_button.winfo_height()<=bottom-4,'Card confirmation is hidden by the taskbar'
            capture('cards-live-suggestion',cards.win)
            cards.confirm();root.update()
            assert cards.selected() is None and 'disabled' in cards.confirm_button.state(),'Completed card returned to the pending queue'
            assert 'All available cards are reviewed' in cards.status.cget('text'),'Card completion state is missing'
            cards.show_reviewed.set(True);cards.refresh();root.update()
            assert cards.vendor_number.get()=='9' and cards.stage.get()=='Full','Reviewed card cannot be reopened'
            assert file_digest(path)==sha,'Card review altered the original photo'
            capture('cards-reviewed',cards.win);cards.close();root.update()
            result['card_review_checks']=['live_suggestions','manual_values_preserved','explicit_stage_choice','completed_queue','reopen_reviewed_card','original_unchanged']
            # Run the actual packaged import path, then inspect its document
            # confirmation at a short window height. No source data is used.
            import fitz
            from tkinter import messagebox
            bid=Path(folder)/'Synthetic Vendor Bid for Review.pdf'
            with fitz.open() as doc:
                doc.new_page().insert_text((40,40),'BID\nTOTAL $1,400.00\n40 CYD');doc.save(bid)
            original=bid.read_bytes();notice=messagebox.showinfo
            try:
                messagebox.showinfo=lambda *a,**k:None
                assert app._import_paths([bid]),'Packaged vendor import failed'
                count=len(app.case['imported_files'])
                assert app._import_paths([bid]) and len(app.case['imported_files'])==count,'Exact duplicate import was not skipped'
            finally:messagebox.showinfo=notice
            document=next(d for d in app.case['package_documents'] if d.get('name')==bid.name)
            assert Path(document['path']).read_bytes()==original and not document['confirmed'],'Import changed or confirmed a source'
            index=app.case['package_documents'].index(document);app.documents.selection_set(str(index));app.edit_document();root.update()
            dialog=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Review Package Document');dialog.geometry('640x420');root.update()
            def descendants(parent):
                for w in parent.winfo_children():yield w;yield from descendants(w)
            confirm=next(w for w in descendants(dialog) if w.winfo_class()=='TButton' and w.cget('text')=='Confirm Document')
            assert confirm.winfo_ismapped() and confirm.winfo_rooty()+confirm.winfo_height()<=dialog.winfo_rooty()+dialog.winfo_height(),'Document confirmation is not reachable'
            capture('document-review-short',dialog)
            canvas=next(w for w in descendants(dialog) if isinstance(w,tk.Canvas));canvas.yview_moveto(1);root.update()
            assert canvas.yview()[0]>0,'Long document details cannot be scrolled'
            capture('document-review-scrolled',dialog);dialog.destroy();root.update()
            result['import_document_checks']=['background_import','exact_duplicate_skipped','original_preserved','unconfirmed_document','short_window_confirmation','scrollable_document_details']
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
