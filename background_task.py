"""Run file work off the UI thread while protecting the active case."""
import queue
import threading
import tkinter as tk
from tkinter import ttk


def run_file_task(parent,title,worker):
    cancel=threading.Event();events=queue.Queue();outcome={}
    win=tk.Toplevel(parent);win.configure(background=parent.cget('background') if 'background' in parent.keys() else '#f2f5f8');win.title(title);win.geometry('470x230');win.resizable(False,False);win.transient(parent)
    actions=ttk.Frame(win);actions.pack(side='bottom',fill='x',padx=20,pady=(0,12))
    ttk.Label(win,text=title,font=('',14,'bold')).pack(anchor='w',padx=20,pady=(18,8))
    label=ttk.Label(win,text='Preparing files...',wraplength=420);label.pack(fill='x',padx=20)
    bar=ttk.Progressbar(win,mode='indeterminate');bar.pack(side='bottom',fill='x',padx=20,pady=12);bar.start()
    def stop():cancel.set();label.configure(text='Cancelling after the current file...');button.configure(state='disabled')
    button=ttk.Button(actions,text='Cancel',command=stop);button.pack(side='right')
    win.protocol('WM_DELETE_WINDOW',stop);win.grab_set()
    def work():
        try:events.put(('done',worker(cancel,lambda message:events.put(('progress',message)))))
        except Exception as exc:events.put(('error',exc))
    def poll():
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='progress':label.configure(text=value)
                else:
                    outcome[kind]=value;bar.stop();win.grab_release();win.destroy();return
        except queue.Empty:win.after(75,poll)
    threading.Thread(target=work,daemon=True).start();win.after(50,poll);parent.wait_window(win)
    if 'error' in outcome:raise outcome['error']
    if 'done' not in outcome:raise InterruptedError('The operation was interrupted.')
    return outcome['done']
