import tempfile,unittest,shutil
from pathlib import Path
from cor_package import bid_requirements,validate,bid_fingerprint
from test_cor_package import fixture

class DebrisRequirementTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.case=fixture(self.root)
  self.case.update(rate_per_cyd='100',invoice_amount_usd='2999.00')
  for bid in self.case['package_documents']:
   if bid['role']=='bid':bid['amount']='5000'
 def tearDown(self):self.temp.cleanup()
 def test_three_bids_with_quantities_pass(self):self.assertEqual(bid_requirements(self.case),[])
 def test_two_bids_are_flagged_even_below_45_per_cyd(self):
  bids=[d for d in self.case['package_documents'] if d['role']=='bid']
  self.case['package_documents'].remove(bids[-1]);self.case['rate_per_cyd']='35'
  for load in self.case['loads']:load['length_ft']='40'
  self.assertTrue(any('2 of 3' in x for x in validate(self.case)))
 def test_missing_quantity_does_not_count(self):
  next(d for d in self.case['package_documents'] if d['role']=='bid')['debris_quantity_cyd']=''
  self.assertTrue(any('debris quantity shown' in x for x in bid_requirements(self.case)))
  self.assertTrue(any('2 of 3' in x for x in bid_requirements(self.case)))
 def test_duplicate_copy_does_not_count_as_another_bid(self):
  bids=[d for d in self.case['package_documents'] if d['role']=='bid']
  copy=self.root/'renamed.pdf';shutil.copyfile(bids[0]['path'],copy);bids[-1]['path']=str(copy)
  self.assertTrue(any('2 of 3' in x for x in bid_requirements(self.case)))
 def test_quantity_changes_invalidate_bid_confirmation(self):
  old=bid_fingerprint(self.case)
  next(d for d in self.case['package_documents'] if d['role']=='bid')['debris_quantity_cyd']='40'
  self.assertNotEqual(old,bid_fingerprint(self.case))
 def test_missing_rbb_invoice_during_and_receipt_are_flagged(self):
  self.case['package_documents']=[d for d in self.case['package_documents'] if d['role']=='bid']
  self.case['during_photos']=[];self.case['loads'][0]['photos'].pop('receipt')
  text='\n'.join(validate(self.case))
  for expected in ['RBB / Bluebook','Final Invoice','during','receipt']:self.assertIn(expected,text)

if __name__=='__main__':unittest.main()
