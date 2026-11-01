import tempfile
import unittest
from pathlib import Path
import fitz
from PIL import Image
from ed_app import make_case, default_load
from calculator_evidence import URL, measurement_signature, file_digest
from cor_package import assemble, totals, description, bid_fingerprint, financial_fingerprint, validate, parse_pages, document_suggestions, labeled_measurements, extract_costs

def fixture(folder):
    case=make_case('TEST-001','','Test Vendor',3,35)
    case.update(verified_first_10_amount='300',first_10_prior_work='no',invoice_quantity_basis='includes',
                invoice_deduction_status='yes',invoice_deduction_usd='300',invoice_amount_usd='1099.65',
                invoice_quantity_cyd='39.99',financial_confirmation_hash='synthetic-confirmation',bid_review_confirmed=True)
    image=folder/'synthetic.png';Image.new('RGB',(400,300),'#a6c9d9').save(image)
    for load in case['loads']:
        load.update(length_ft=12,width_ft=6,side_height_ft=5,fill_fraction='1',measurements_confirmed=True,
                    container_name='Synthetic Container',photos={key:str(image) for key in ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt')},
                    disposal_photo=str(image),evidence_first_10_cyd=str(image),extra_measurement_photos=[str(image)]*3)
        load['calculator_evidence']=dict(path=str(image),source_url=URL,user_confirmed=True,sha256=file_digest(image),measurement_signature=measurement_signature(load))
    for key in ('before_photos','during_photos','after_photos'):case[key]=[str(image)]
    documents=[]
    for role,label,pages,amount in [('invoice','SYNTHETIC INVOICE',2,''),('bid','SYNTHETIC BID',1,'1400'),('estimate','SYNTHETIC REPAIR SUMMARY',1,'')]:
        path=folder/(role+'.pdf');doc=fitz.open()
        for i in range(pages):doc.new_page().insert_text((50,50),label+f' PAGE {i+1}')
        doc.save(path);doc.close()
        documents.append(dict(path=str(path),name=path.name,role=role,pages='',confirmed=True,amount=amount,vendor='Test Vendor'))
    case['package_documents']=documents;case['bid_confirmation_hash']=bid_fingerprint(case)
    case['financial_confirmation_hash']=financial_fingerprint(case)
    return case

class CompletePackageTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.case=fixture(self.folder)
    def tearDown(self):self.temp.cleanup()

    def test_complete_pdf_preserves_document_order_and_pages(self):
        report=assemble(self.case,self.folder/'package.pdf')
        self.assertEqual(report['issues'],[])
        with fitz.open(self.folder/'package.pdf') as doc:
            self.assertIn('INVOICE PAGE 1',doc[0].get_text());self.assertIn('INVOICE PAGE 2',doc[1].get_text())
            self.assertIn('BID PAGE 1',doc[2].get_text());self.assertIn('REPAIR SUMMARY',doc[3].get_text())
            text=''.join(page.get_text() for page in doc)
            self.assertIn('Load 3',text);self.assertIn('Before Photos',text);self.assertIn('During Photos',text);self.assertIn('After Photos',text)
        self.assertTrue((self.folder/'COR_Request_Description.txt').is_file())

    def test_request_description_uses_fixed_allowance_and_consistent_money(self):
        text=description(self.case)
        self.assertIn('39.99 CYDS $1,399.65',text)
        self.assertIn('FSM EXPENSE 10 CYDS: -$300.00',text)
        self.assertIn('29.99 CYDS $1,099.65',text)
        self.assertNotIn('350.00',text)

    def test_different_containers_and_partial_loads(self):
        self.case['loads']=self.case['loads'][:2]
        self.case['loads'][1].update(length_ft=10,width_ft=5,side_height_ft=4,fill_fraction='.5')
        self.assertEqual(str(totals(self.case)['quantity']),'17.03')

    def test_missing_documents_cannot_produce_ready_description(self):
        self.case['package_documents']=[]
        report=assemble(self.case,self.folder/'package.pdf')
        self.assertTrue(report['issues']);self.assertFalse((self.folder/'COR_Request_Description.txt').exists())

    def test_old_description_removed_when_new_export_is_incomplete(self):
        assemble(self.case,self.folder/'package.pdf');self.case['loads'][0]['length_ft']=15
        assemble(self.case,self.folder/'package.pdf')
        self.assertFalse((self.folder/'COR_Request_Description.txt').exists())

    def test_page_ranges_preserve_pages_and_reject_overlap(self):
        self.assertEqual(parse_pages('1-2, 4',4),[0,1,3])
        with self.assertRaises(ValueError):parse_pages('1-3, 2',4)
        with self.assertRaises(ValueError):parse_pages('7',4)
        self.case['package_documents'].append(dict(self.case['package_documents'][0]))
        self.assertTrue(any('Overlapping' in issue for issue in validate(self.case)))

    def test_labeled_measurements_only_and_multipage_document_suggestion(self):
        self.assertEqual(labeled_measurements('Length: 12 ft Width: 6 ft Height: 5 ft'),dict(length_ft='12',width_ft='6',side_height_ft='5'))
        self.assertEqual(labeled_measurements('12 x 6 x 5'),{})
        suggestions=document_suggestions(dict(path=self.case['package_documents'][0]['path'],name='invoice.pdf'))
        self.assertEqual(suggestions[0]['role'],'invoice');self.assertEqual(suggestions[0]['pages'],'1-2')

    def test_cost_extraction_requires_explicit_unambiguous_labels(self):
        values=extract_costs('Removed and disposed 39.99 CYDs @ $35.00 per cubic yard\nTOTAL $1,099.65\nfirst 10 CYDs ($300.00)')
        self.assertEqual(values['invoice_quantity_cyd'],'39.99')
        self.assertEqual(values['invoice_amount_usd'],'1099.65')
        self.assertEqual(values['invoice_deduction_usd'],'300.00')
        self.assertEqual(values['rate_per_cyd'],'35.00')

    def test_ambiguous_document_totals_are_not_guessed(self):
        values=extract_costs('TOTAL $900.00\nTOTAL $1200.00')
        self.assertNotIn('invoice_amount_usd',values)

    def test_source_failure_does_not_replace_existing_pdf(self):
        path=self.folder/'package.pdf';path.write_bytes(b'previous-output')
        self.case['package_documents'][0]['pages']='99'
        with self.assertRaises(ValueError):assemble(self.case,path)
        self.assertEqual(path.read_bytes(),b'previous-output')

if __name__=='__main__':unittest.main()
