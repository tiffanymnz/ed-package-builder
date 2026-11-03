import unittest,tempfile
from pathlib import Path
from cor_package import totals,description,financial_fingerprint,validate,required_bid_count,assemble
from test_cor_package import fixture

class HudRequestRulesTests(unittest.TestCase):
 def case(self):
  return dict(loads=[dict(length_ft='19.5',width_ft='7.8',side_height_ft='6.5'),dict(length_ft='19.5',width_ft='7.8',side_height_ft='6.5')],rate_per_cyd='45',verified_first_10_amount='300',first_10_prior_work='yes')
 def test_approved_package_calculation_ignores_separate_300_credit(self):
  value=totals(self.case())
  self.assertEqual(str(value['quantity']),'73.24');self.assertEqual(str(value['gross']),'3295.80')
  self.assertEqual(str(value['allowance']),'450.00');self.assertEqual(str(value['request']),'2845.80')
  self.assertEqual(str(value['request_quantity']),'63.24')
 def test_rate_changes_recalculate_hud_deduction(self):
  case=self.case();case['rate_per_cyd']='35'
  self.assertEqual(str(totals(case)['allowance']),'350.00')
  case['verified_first_10_amount']='9999'
  self.assertEqual(str(totals(case)['allowance']),'350.00')
 def test_description_reproduces_approved_case_arithmetic(self):
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case.update(self.case())
   case.update(invoice_amount_usd='2845.80',invoice_quantity_cyd='73.24',invoice_deduction_usd='450')
   amounts=iter(['3330','3700','3650'])
   for bid in case['package_documents']:
    if bid['role']=='bid':bid['amount']=next(amounts)
   from cor_package import bid_fingerprint
   case['bid_confirmation_hash']=bid_fingerprint(case);case['financial_confirmation_hash']=financial_fingerprint(case)
   text=description(case)
   for fragment in ['73.24 CYDS $3,295.80','FSM EXPENSE 10 CYDS: -$450.00','63.24 CYDS $2,845.80']:self.assertIn(fragment,text)
 def test_quantity_below_ten_never_creates_negative_request(self):
  case=self.case();case['loads']=[dict(length_ft=9,width_ft=3,side_height_ft=3)]
  value=totals(case);self.assertEqual(str(value['quantity']),'3.00');self.assertEqual(str(value['request']),'0.00')
  self.assertEqual(str(value['allowance']),'135.00')
 def test_existing_invoice_deduction_is_not_subtracted_twice(self):
  for status,invoice in [('yes','2845.80'),('no','3295.80')]:
   case=self.case();case.update(invoice_deduction_status=status,invoice_amount_usd=invoice,invoice_deduction_usd='450' if status=='yes' else '0')
   self.assertEqual(str(totals(case)['request']),'2845.80')
 def test_under_over_and_ambiguous_bid_thresholds(self):
  self.assertEqual(required_bid_count(dict(invoice_amount_usd='2000')),1)
  self.assertEqual(required_bid_count(dict(invoice_amount_usd='3000')),3)
  self.assertIsNone(required_bid_count(dict(invoice_amount_usd='2500')))
  case=self.case();case.update(rate_per_cyd='38',invoice_amount_usd='2403.12')
  self.assertIsNone(required_bid_count(case))
 def test_photo_measurement_difference_flags_invoice_instead_of_overwriting(self):
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case['invoice_quantity_cyd']='40.99'
   self.assertTrue(any('photo-supported' in text for text in validate(case)))
   self.assertEqual(case['loads'][0]['length_ft'],12)
 def test_three_complete_bids_cover_either_unresolved_threshold_rule(self):
  from cor_package import bid_requirements
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case['invoice_amount_usd']='2500'
   self.assertIsNone(required_bid_count(case));self.assertEqual(bid_requirements(case),[])
 def test_legacy_financial_confirmation_cannot_generate_description(self):
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case['financial_confirmation_hash']='old-rule-hash'
   with self.assertRaises(ValueError):description(case)
 def test_invoice_excluding_first_ten_is_not_deducted_again(self):
  with tempfile.TemporaryDirectory() as folder:
   case=fixture(Path(folder));case.update(invoice_quantity_basis='excludes',invoice_quantity_cyd='29.99',invoice_amount_usd='1049.65',invoice_deduction_status='no',invoice_deduction_usd='0')
   case['financial_confirmation_hash']=financial_fingerprint(case)
   self.assertEqual(validate(case),[])
 def test_attached_work_order_precedes_invoice_and_approval_is_preserved(self):
  import fitz
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);case=fixture(root)
   for role in ['work_order','approval']:
    path=root/(role+'.pdf');doc=fitz.open();doc.new_page().insert_text((50,50),'SYNTHETIC '+role.upper());doc.save(path);doc.close()
    case['package_documents'].append(dict(role=role,path=str(path),name=path.name,pages='',confirmed=True))
   from cor_package import bid_fingerprint
   case['bid_confirmation_hash']=bid_fingerprint(case);case['financial_confirmation_hash']=financial_fingerprint(case)
   assemble(case,root/'out.pdf')
   with fitz.open(root/'out.pdf') as doc:
    self.assertIn('APPROVAL',doc[0].get_text());self.assertIn('WORK_ORDER',doc[1].get_text());self.assertIn('INVOICE',doc[2].get_text())

if __name__=='__main__':unittest.main()
