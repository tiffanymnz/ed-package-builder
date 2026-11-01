"""ED Package Builder v3 — offline Windows-first case workspace.
Human-assigned images; no claimed AI automation. Launch: python ed_app.py
"""
import json,hashlib,shutil,zipfile,os,subprocess,sys,tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from ed_builder import build,volume,ALL
from evidence_engine import export as triage_export
from visual_gallery import gallery as open_visual_gallery
from visual_intake import export as visual_intake_export
from ground_truth_review import sample_archives, open_review
from image_suggestions import candidates as suggest_candidates
from evidence_timeline import make_report as make_timeline
from evidence_matcher import rank_similar
from text_evidence import analyze as ocr_analyze, available as ocr_available
from evidence_audit import write_report, collect as audit_evidence
from vision_adapter import analyze_local

BASE=Path.home()/ 'ED_Package_Builder_Cases'
IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
ACCEPT=IMAGE_EXT|{'.pdf','.docx','.txt'}
PHOTO_SLOTS=[x for x in ALL if x!='calculator']+['disposal_photo','first_10_proof','measurement_extra_1','measurement_extra_2','measurement_extra_3']
PHASES=['before_photos','during_photos','after_photos','financial_pdfs']

def safe(s):return ''.join(x if x.isalnum() or x in '-_' else '_' for x in s)[:80]
def as_number(value,default=0):
    try:return float(value)
    except:return default

def default_load(n):
    return {'name':f'Load {n}','length_ft':'','width_ft':'','side_height_ft':'','overage_height_ft':0,'overage_cyd':0,'overage_note':'','measured_load_cyd':None,'photos':{},'extra_measurement_photos':[],'disposal_photo':'','evidence_first_10_cyd':''}

def make_case(case,address,vendor,loads,rate):
    return dict(case_number=case,address=address,vendor=vendor,rate_per_cyd=rate,deduct_first_10_cyd=True,
      loads=[default_load(i) for i in range(1,loads+1)],financial_pdfs=[],before_photos=[],during_photos=[],after_photos=[],
      invoice_quantity_cyd='',invoice_amount_usd='',invoice_deduction_usd='',
      invoice_quantity_basis='unknown',invoice_deduction_status='unknown',first_10_prior_work='unknown',verified_first_10_amount='',financial_confirmation_hash='',financial_confirmation_note='',
      photo_assignments={},imported_files=[],review_confirmed=False)

class App:
 def __init__(self,root):
    self.root=root;root.title('ED Package Builder — Portable Pilot (v16)');root.geometry('1160x790')
    self.case=None;self.case_dir=None;self.selected_photo=None;self.photos=[];self.thumb_cache={};self.vars={}
    self.bar=ttk.Frame(root,padding=12);self.bar.pack(fill='x')
    ttk.Label(self.bar,text='ED PACKAGE BUILDER',font=('Segoe UI',16,'bold')).pack(side='left')
    for label,fn in [('New Case',self.new_case),('Open Case',self.open_case),('Save',self.save),('Import Folder',self.import_files),('Import ZIPs',self.import_zips),('Analyze Files',self.analyze_files),('Visual Gallery',self.visual_gallery),('Visual Triage',self.visual_triage),('Timeline Review',self.timeline_review),('Similar Photos',self.similar_photos),('Read Photo Text',self.read_photo_text),('Local AI Review',self.local_ai_review),('Audit Evidence',self.audit_evidence),('Verify Samples',self.verify_samples),('Suggest Sample Types',self.suggest_sample_types),('Generate Draft',self.generate),('Transmittal PDF',self.transmittal)]:
       ttk.Button(self.bar,text=label,command=fn).pack(side='right',padx=3)
    self.status=tk.StringVar(value='Create or open a case. Evidence matching remains manual; validation is automatic.')
    ttk.Label(root,textvariable=self.status,foreground='#57616b').pack(fill='x',padx=14)
    self.guide=ttk.Frame(root,padding=(12,5));self.guide.pack(fill='x')
    self.guide_title=ttk.Label(self.guide,text='Start with a case, add all vendor files, review issues, then generate a draft.',font=('Segoe UI',11,'bold'));self.guide_title.pack(anchor='w')
    nav=ttk.Frame(self.guide);nav.pack(fill='x',pady=8)
    self.nav=nav
    self.tabs=ttk.Notebook(root);self.tabs.pack(expand=True,fill='both',padx=12,pady=8)
    self.case_tab=ttk.Frame(self.tabs,padding=10);self.evidence_tab=ttk.Frame(self.tabs,padding=10);self.finance_tab=ttk.Frame(self.tabs,padding=10);self.check_tab=ttk.Frame(self.tabs,padding=10)
    for tab,title in [(self.case_tab,'1 · Case & Loads'),(self.evidence_tab,'2 · Import & Photos'),(self.finance_tab,'3 · Invoice'),(self.check_tab,'4 · Review Issues')]:self.tabs.add(tab,text=title)
    self.draw_case();self.draw_evidence();self.draw_finance();self.draw_checks()
    for i,(label,desc) in enumerate([('1  Case','Details & load measurements'),('2  Photos','Import and assign evidence'),('3  Invoice','Verify first 10 CYD deduction'),('4  Issues','Validate before export')]):
       b=ttk.Button(nav,text=label,command=lambda j=i:self.tabs.select(j));b.pack(side='left',padx=(0,10))
    ttk.Button(nav,text='How it works',command=self.help).pack(side='right')
    self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.update_guide())

 def update_guide(self):
    notes=['Step 1: Confirm the case and enter vendor-measured dimensions for each load.','Step 2: Import all source files, then assign original images to the matching load or property section.','Step 3: Confirm case-specific first-10-CYD amount, invoice quantity, and existing deduction.','Step 4: Resolve missing evidence and invoice conflicts. Generate only a DRAFT until final human review.']
    try:self.guide_title.configure(text=notes[self.tabs.index(self.tabs.select())])
    except Exception:pass
 def help(self):
    messagebox.showinfo('ED Package Builder — How to use',
      '1. NEW CASE: enter case number, vendor and estimated load count.\n\n'
      '2. IMPORT: select a folder with ReamsView downloads, saved Outlook files or ZIPs. You can import again after corrections.\n\n'
      '3. PHOTOS: choose the load and required slot, preview the file, then click Assign. This version DOES NOT identify unlabeled photos automatically.\n\n'
      '4. MEASUREMENTS: enter documented length, width and height in feet, plus supported overage.\n\n'
      '5. INVOICE: manually confirm applicable deduction amount and whether invoice CYD includes the first 10.\n\n'
      '6. REVIEW: inspect all exceptions. Draft exports are not COR approvals. Save is automatic after assignments; use Save for field edits.')

 def require(self):
    if self.case is None:messagebox.showwarning('Open a case','Create or open a case first.');return False
    return True
 def new_case(self):
    win=tk.Toplevel(self.root);win.title('New case');win.geometry('425x300');win.transient(self.root);win.grab_set()
    fields=[('Case number','093-EXAMPLE'),('Property address',''),('Vendor',''),('Number of loads','3'),('ED rate per CYD','35')]
    entries={}
    for i,(lab,default) in enumerate(fields):
       ttk.Label(win,text=lab).grid(row=i,column=0,padx=10,pady=8,sticky='w');e=ttk.Entry(win,width=27);e.insert(0,default);e.grid(row=i,column=1,pady=8);entries[lab]=e
    def create():
       try:
          n=int(entries['Number of loads'].get());assert 1<=n<=150
          case=entries['Case number'].get().strip();assert case
          d=BASE/safe(case);d.mkdir(parents=True,exist_ok=True)
          if (d/'case.json').exists():raise ValueError('Case already exists; use Open Case')
          self.case=make_case(case,entries['Property address'].get(),entries['Vendor'].get(),n,as_number(entries['ED rate per CYD'].get(),35));self.case_dir=d;self.save();self.refresh();win.destroy()
       except Exception as e:messagebox.showerror('Case error',str(e))
    ttk.Button(win,text='Create Case',command=create).grid(row=6,column=1,sticky='e',pady=12)
 def open_case(self):
