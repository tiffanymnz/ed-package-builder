"""Windowed entry point with a readable startup failure and a local crash log."""
import os,sys,traceback
from pathlib import Path

def launch(entry=None):
    # Windowed Windows executables have no stdout/stderr streams.
    for stream in ('stdout','stderr'):
        if getattr(sys,stream) is None:setattr(sys,stream,open(os.devnull,'w',encoding='utf-8'))
    try:
        if entry is None:
            from ed_app import main
            entry=main
        result=entry()
        return 0 if result is None else result
    except Exception:
        message='ED Package Builder could not start.'
        try:
            folder=Path(os.environ.get('ED_STARTUP_LOG_DIR') or Path(os.environ.get('LOCALAPPDATA') or Path.home())/'EDPackageBuilder'/'Logs')
            folder.mkdir(parents=True,exist_ok=True);path=folder/'startup-error.txt'
            path.write_text(traceback.format_exc(),encoding='utf-8');message+='\n\nDetails were saved to:\n'+str(path)
        except OSError:message+='\n\nThe startup error log could not be saved.'
        if not any(flag in sys.argv for flag in ('--smoke-test','--vision-smoke-test','--ui-smoke-test')):
            try:
                from tkinter import messagebox
                messagebox.showerror('Unable to Open ED Package Builder',message)
            except Exception:pass
        return 1

if __name__=='__main__':sys.exit(launch())
