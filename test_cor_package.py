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
    case.update(verified_first_10_amount='350',first_10_prior_work='no',invoice_quantity_basis='includes',
                invoice_deduction_status='yes',invoice_deduction_usd='350',invoice_amount_usd='1049.65',
                invoice_quantity_cyd='39.99',financial_confirmation_hash='synthetic-confirmation',bid_review_confirmed=True)
    image=folder/'synthetic.png';Image.new('RGB',(400,300),'#a6c9d9').save(image)
    for load_number,load in enumerate(case['loads'],1):
        load.update(length_ft=12,width_ft=6,side_height_ft=5,fill_fraction='1',measurements_confirmed=True,
                    container_name='Synthetic Container',photos={key:str(image) for key in ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt')},
                    disposal_photo=str(image),evidence_first_10_cyd=str(image),extra_measurement_photos=[str(image)]*3)
        for stage_number,slot in enumerate(('empty','quarter','half','three_quarters','full_1','full_2')):
            view=folder/f'load-{load_number}-{slot}.png'
            Image.new('RGB',(80,60),(load_number*50,stage_number*35,90)).save(view)
            load['photos'][slot]=str(view)
        load['calculator_evidence']=dict(path=str(image),source_url=URL,user_confirmed=True,sha256=file_digest(image),measurement_signature=measurement_signature(load))
    for key in ('before_photos','during_photos','after_photos'):case[key]=[str(image)]
    documents=[]
    for index,(role,label,pages,amount) in enumerate([('invoice','SYNTHETIC INVOICE',2,''),('bid','SYNTHETIC BID',1,'1400'),('bid','SYNTHETIC BID TWO',1,'1500'),('bid','SYNTHETIC BID THREE',1,'1600'),('estimate','SYNTHETIC REPAIR SUMMARY',1,'')]):
        path=folder/(role+str(index)+'.pdf');doc=fitz.open()
        for i in range(pages):doc.new_page().insert_text((50,50),label+f' PAGE {i+1}')
        doc.save(path);doc.close()
        documents.append(dict(path=str(path),name=path.name,role=role,pages='',confirmed=True,amount=amount,vendor='Test Vendor',debris_quantity_cyd='39.99' if role=='bid' else ''))
    case['package_documents']=documents;case['bid_confirmation_hash']=bid_fingerprint(case)
    case['financial_confirmation_hash']=financial_fingerprint(case)
    return case

class CompletePackageTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.case=fixture(self.folder)
    def tearDown(self):self.temp.cleanup()

    def test_approved_template_geometry_and_full_page_receipt(self):
        from cor_package import template_load_pages
        with fitz.open() as doc:
            template_load_pages(doc,self.case['loads'][0],1)
            self.assertEqual(len(doc),3)
            self.assertIn('LOAD 1',doc[0].get_text())
            self.assertIn('Cubic Yard Calculation',doc[0].get_text())
            self.assertEqual(doc[1].get_text().count('Full Container'),2)
            self.assertIn('See Following Page',doc[1].get_text())
            rects=[item['rect'] for item in doc[1].get_drawings()]
            self.assertIn(fitz.Rect(72,482,540,707),rects)
            self.assertTrue(doc[2].get_image_info())
            self.assertEqual(doc[2].get_text(),'')

    def test_missing_receipt_is_visible_without_empty_extra_page(self):
        from cor_package import template_load_pages
        self.case['loads'][0]['photos'].pop('receipt')
        with fitz.open() as doc:
            template_load_pages(doc,self.case['loads'][0],1)
            self.assertEqual(len(doc),2)
            self.assertIn('Evidence Not Attached',doc[1].get_text())
            self.assertNotIn('See Following Page',doc[1].get_text())

    def test_property_grid_preserves_nine_per_page_and_remaining_photos(self):
        from cor_package import property_photo_pages
        paths=[self.case['loads'][0]['photos']['height']]*10
        with fitz.open() as doc:
            property_photo_pages(doc,paths,'Before Photos')
            self.assertEqual(len(doc),2)
            self.assertEqual(len(doc[0].get_image_info()),9)
            self.assertEqual(len(doc[1].get_image_info()),1)
            self.assertIn('Before Photos',doc[0].get_text())
            for image in doc[0].get_image_info():
                self.assertTrue(fitz.Rect(27,36,585,756).contains(fitz.Rect(image['bbox'])))

    def test_itemized_invoice_extraction_reads_printed_values_only(self):
        text='Rate per Cubic Yard: $45.00 per cyds\nLoad 1: 19.5 x 7.8 x 6.5 = 36.62 cyds\nLoad 2: 19.5 x 7.8 x 6.5 = 36.62 cyds\nSub Total:\n$3,295.80\n10 cyds FSM responsibility\n$45.00\n($450.00)\nTotal: $2,845.80\nDisposal Fees\n$690.00'
        self.assertEqual(extract_costs(text),dict(invoice_amount_usd='2845.80',rate_per_cyd='45.00',invoice_quantity_cyd='73.24',invoice_deduction_usd='450.00'))
        self.assertEqual(labeled_measurements(text),{})

    def test_conflicting_rate_and_quantity_remain_blank(self):
        values=extract_costs('Rate per CYD: $45.00\nAt $50.00 per cubic yard\nLoad 1: L x W x H = 36.62 CYD\nTOTAL CYDS: 70.00')
        self.assertNotIn('invoice_quantity_cyd',values)
        self.assertNotIn('rate_per_cyd',values)

    def test_repeated_load_lines_are_not_double_counted(self):
        line='Load 1: 19 x 7 x 6 = 29.56 CYD\n'
        self.assertEqual(extract_costs(line*2)['invoice_quantity_cyd'],'29.56')
        self.assertNotIn('invoice_quantity_cyd',extract_costs(line+'Load 1: 20 x 7 x 6 = 31.11 CYD'))

    def test_unlabeled_dimensions_do_not_become_invoice_quantity(self):
        self.assertNotIn('invoice_quantity_cyd',extract_costs('19.5 x 7.8 x 6.5\nTotal $200.00'))

    def test_malformed_currency_is_not_silently_repaired(self):
        self.assertNotIn('invoice_amount_usd',extract_costs('TOTAL $3,3650.00'))
        self.assertNotIn('rate_per_cyd',extract_costs('Rate per CYD: $4,50.00'))

    def test_compact_load_card_needs_explicit_axes_and_units(self):
        self.assertEqual(labeled_measurements('Load #2\n19 ft x 7.8 ft x 6.5 ft\nL W H'),dict(length_ft='19',width_ft='7.8',side_height_ft='6.5'))
        self.assertEqual(labeled_measurements('19 ft x 7.8 ft x 6.5 ft'),{})
        self.assertEqual(labeled_measurements('19 x 7.8 x 6.5\nL W H'),{})
        self.assertEqual(labeled_measurements('19 ft x 7.8 ft x 6.5 ft\nH W L'),dict(side_height_ft='19',width_ft='7.8',length_ft='6.5'))

    def test_conflicting_card_dimensions_are_not_guessed(self):
        values=labeled_measurements('19 ft x 7.8 ft x 6.5 ft\nL W H\n19.5 ft x 7.8 ft x 6.5 ft\nL W H')
        self.assertNotIn('length_ft',values)

    def test_filename_never_becomes_load_stage_or_dimensions(self):
        from cor_package import photo_suggestion
        row=photo_suggestion(dict(path='test.jpg',name='Load 2 Empty Height 6 ft.jpg'))
        self.assertIsNone(row['load']);self.assertIsNone(row['slot']);self.assertEqual(row['dimensions'],{})

    def test_multiple_loads_and_document_text_do_not_assign_photo_evidence(self):
        from cor_package import photo_suggestion
        self.assertIsNone(photo_suggestion(dict(path='x.jpg'),'Load 1 and Load 2')['load'])
        row=photo_suggestion(dict(path='x.jpg'),'INVOICE\nLoad 2\nHeight 6 ft\nEmpty Container')
        self.assertIsNone(row['load']);self.assertIsNone(row['slot']);self.assertEqual(row['dimensions'],{})

    def test_only_one_progression_label_can_be_suggested(self):
        from cor_package import photo_suggestion
        self.assertEqual(photo_suggestion(dict(path='x.jpg'),'Load #2\n1/2 Full')['slot'],'half')
        self.assertIsNone(photo_suggestion(dict(path='x.jpg'),'Load 2\n25% 50% 75% 100%')['slot'])

    def photo_text_case(self):
        from ed_app import default_load
        case=dict(loads=[default_load(1)],imported_files=[],photo_text_cache={})
        for index,text in enumerate(['Load 1\nLength: 19 ft','Load 1\nWidth: 7.8 ft']):
            p=self.folder/f'card{index}.png';Image.new('RGB',(300,300),'white').save(p)
            case['imported_files'].append(dict(path=str(p),name=p.name))
            case['photo_text_cache'][str(p)]=dict(sha256=file_digest(p),text=text)
        return case

    def test_photo_suggestion_batch_checks_fresh_sources_and_invalidates_confirmation(self):
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        case=self.photo_text_case();rows=current_photo_suggestions(case)
        case.update(financial_confirmation_hash='old',bid_confirmation_hash='old',bid_review_confirmed=True)
        self.assertEqual(apply_photo_suggestions(case,rows),1)
        self.assertEqual(case['loads'][0]['length_ft'],'19')
        self.assertEqual(case['loads'][0]['width_ft'],'7.8')
        self.assertFalse(case['loads'][0]['measurements_confirmed'])
        self.assertNotIn('financial_confirmation_hash',case)

    def test_changed_source_rejects_entire_batch_without_partial_updates(self):
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        case=self.photo_text_case();rows=current_photo_suggestions(case)
        Path(rows[1]['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):apply_photo_suggestions(case,rows)
        self.assertEqual(case['loads'][0]['length_ft'],'')

    def test_conflicting_dimensions_and_existing_photo_are_not_overwritten(self):
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        case=self.photo_text_case();rows=current_photo_suggestions(case)
        case['loads'][0]['length_ft']='19.5'
        with self.assertRaises(ValueError):apply_photo_suggestions(case,rows)
        self.assertEqual(case['loads'][0]['length_ft'],'19.5')
        case['loads'][0]['length_ft']='';case['loads'][0]['photos']['length']='another.jpg'
        with self.assertRaises(ValueError):apply_photo_suggestions(case,rows)
        self.assertEqual(case['loads'][0]['photos']['length'],'another.jpg')

    def test_old_filename_suggestions_are_not_reused(self):
        from cor_package import current_photo_suggestions
        case=self.photo_text_case();case['photo_text_cache']={}
        case['photo_suggestions']=[dict(path='Load 1.jpg',load=1,slot='empty',dimensions={})]
        self.assertEqual(current_photo_suggestions(case),[])

    def test_suspicious_load_number_does_not_create_many_empty_loads(self):
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        case=self.photo_text_case()
        for cached in case['photo_text_cache'].values():cached['text']=cached['text'].replace('Load 1','Load 99')
        with self.assertRaises(ValueError):apply_photo_suggestions(case,current_photo_suggestions(case))
        self.assertEqual(len(case['loads']),1)

    def test_progression_photo_alone_does_not_reset_cost_confirmation(self):
        from cor_package import current_photo_suggestions,apply_photo_suggestions
        case=self.photo_text_case()
        for cached in case['photo_text_cache'].values():cached['text']='Load 1\n25% Full'
        case['loads'][0]['measurements_confirmed']=True
        case.update(financial_confirmation_hash='current',bid_review_confirmed=True)
        apply_photo_suggestions(case,current_photo_suggestions(case)[:1])
        self.assertEqual(case['financial_confirmation_hash'],'current')
        self.assertTrue(case['loads'][0]['measurements_confirmed'])

    def test_template_measurements_do_not_require_three_extra_views(self):
        for load in self.case['loads']:load['extra_measurement_photos']=[]
        self.assertEqual(validate(self.case),[])

    def test_missing_template_measurement_still_blocks_without_extras(self):
        self.case['loads'][0]['extra_measurement_photos']=[]
        del self.case['loads'][0]['photos']['height']
        self.assertTrue(any('height' in issue for issue in validate(self.case)))

    def test_unconfirmed_dimensions_still_require_review(self):
        self.case['loads'][0]['measurements_confirmed']=False
        self.assertTrue(any('Confirm the container measurements' in issue for issue in validate(self.case)))

    def test_supporting_measurements_are_retained_but_not_exported_by_default(self):
        original=list(self.case['loads'][0]['extra_measurement_photos'])
        assemble(self.case,self.folder/'package.pdf')
        with fitz.open(self.folder/'package.pdf') as doc:
            self.assertNotIn('Additional Measurement',''.join(page.get_text() for page in doc))
        self.assertEqual(self.case['loads'][0]['extra_measurement_photos'],original)

    def test_supporting_measurements_export_only_for_selected_load(self):
        self.case['loads'][1]['include_supporting_measurements']=True
        assemble(self.case,self.folder/'package.pdf')
        with fitz.open(self.folder/'package.pdf') as doc:
            pages=[page.get_text() for page in doc if 'Additional Measurement' in page.get_text()]
        self.assertEqual(len(pages),1)
        self.assertIn('Load 2 - Supporting Evidence',pages[0])
        self.assertNotIn('Load 1',pages[0])

    def test_complete_pdf_preserves_document_order_and_pages(self):
        report=assemble(self.case,self.folder/'package.pdf')
        self.assertEqual(report['issues'],[])
        with fitz.open(self.folder/'package.pdf') as doc:
            self.assertIn('INVOICE PAGE 1',doc[0].get_text());self.assertIn('INVOICE PAGE 2',doc[1].get_text())
            self.assertIn('BID PAGE 1',doc[2].get_text());self.assertIn('REPAIR SUMMARY',doc[5].get_text())
            text=''.join(page.get_text() for page in doc)
            self.assertIn('Load 3',text);self.assertIn('Before Photos',text);self.assertIn('During Photos',text);self.assertIn('After Photos',text)
        self.assertTrue((self.folder/'COR_Request_Description.txt').is_file())

    def test_request_description_uses_rate_based_deduction_and_consistent_money(self):
        text=description(self.case)
        self.assertIn('39.99 CYDS $1,399.65',text)
        self.assertIn('FSM EXPENSE 10 CYDS: -$350.00',text)
        self.assertIn('29.99 CYDS $1,049.65',text)
        self.assertNotIn('$300.00',text)

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
