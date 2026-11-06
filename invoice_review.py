"""Explicit handling of final invoice versions and combined attachments."""
import hashlib,json
from calculator_evidence import file_digest
def active_invoices(case):return [d for d in case.get('package_documents',[]) if d.get('role')=='invoice']
def checked(d):
 if not d.get('confirmed') or d.get('reviewed_sha256')!=file_digest(d['path']):raise ValueError('Open and confirm every final invoice attachment first.')
def signature(case):
 return hashlib.sha256(json.dumps(sorted((d['path'],file_digest(d['path']),str(d.get('pages',''))) for d in active_invoices(case))).encode()).hexdigest()
def use_invoice_version(case,index):
 docs=case.get('package_documents',[]);chosen=docs[index]
 if chosen.get('role')!='invoice':raise ValueError('Select an invoice.')
 checked(chosen)
 for d in active_invoices(case):file_digest(d['path'])
 digest=file_digest(chosen['path'])
 for d in active_invoices(case):
  if d is not chosen:d.update(role='exclude',superseded_invoice=True,superseded_by_sha256=digest)
 for key in ('financial_confirmation_hash','bid_confirmation_hash','invoice_set_review'):case.pop(key,None)
def confirm_invoice_set(case):
 for d in active_invoices(case):checked(d)
 case['invoice_set_review']={'signature':signature(case),'treatment':'combined_final_figures'}
 case.pop('financial_confirmation_hash',None)
def issues(case):
 if len(active_invoices(case))<2:return []
 try:
  if case.get('invoice_set_review',{}).get('signature')==signature(case):return []
 except OSError:pass
 return ['Choose the final invoice version, or confirm these attachments form one final bill.']
