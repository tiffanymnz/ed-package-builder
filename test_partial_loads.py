import copy,tempfile,unittest
from pathlib import Path
from load_requirements import required_loading_slots,applicable
class PartialLoadTests(unittest.TestCase):
 def test_only_confirmed_standard_partial_fills_reduce_requirements(self):
  for fraction,expected in [('.25',{'empty','quarter'}),('.5',{'empty','quarter','half'}),('.75',{'empty','quarter','half','three_quarters'})]:
   self.assertEqual(required_loading_slots(dict(fill_fraction=fraction,measurements_confirmed=True)),expected)
   self.assertEqual(len(required_loading_slots(dict(fill_fraction=fraction))),6)
  for fraction in ('bad','0','1','NaN'):
   self.assertEqual(len(required_loading_slots(dict(fill_fraction=fraction,measurements_confirmed=True))),6)
 def partial(self,folder):
  from test_cor_package import fixture
  case=fixture(folder);load=case['loads'][0];load['fill_fraction']='.5'
  for slot in ('three_quarters','full_1','full_2'):load['photos'].pop(slot)
  return case,load
 def test_validation_does_not_require_later_stages(self):
  from cor_package import validate
  from evidence_audit import collect
  with tempfile.TemporaryDirectory() as d:
   case,load=self.partial(Path(d));issues=validate(case)
   self.assertFalse(any('Add three quarters' in p or 'Add full ' in p for p in issues))
   self.assertFalse(any(p['type']=='missing_slot' and p['load']==1 and any(k in p['detail'] for k in ('three_quarters','full_1','full_2')) for p in collect(case)['issues']))
 def test_higher_stage_placement_requires_correction(self):
  from cor_package import validate
  with tempfile.TemporaryDirectory() as d:
   case,load=self.partial(Path(d));load['photos']['full_1']=load['photos']['height']
   self.assertTrue(any('conflicts with the confirmed partial fill' in p for p in validate(case)))
 def test_partial_pdf_has_final_fill_and_not_applicable_boxes(self):
  import fitz
  from cor_package import template_load_pages
  with tempfile.TemporaryDirectory() as d:
   case,load=self.partial(Path(d))
   with fitz.open() as pdf:
    template_load_pages(pdf,load,1);self.assertIn('FINAL FILL 50',pdf[0].get_text());self.assertEqual(pdf[1].get_text().count('Not Applicable'),3)
 def test_filter_selection_is_nonmutating_and_spans_pages(self):
  from photo_flow import PhotoFlowWindow
  from types import SimpleNamespace
  from unittest.mock import Mock
  case={};rows=[dict(path=str(i)) for i in range(20)]
  window=SimpleNamespace(app=SimpleNamespace(case=case),case=case,filtered=lambda:rows,selected=set(),render=Mock(),review_help=Mock())
  PhotoFlowWindow.select_filtered(window);self.assertEqual(len(window.selected),20);self.assertEqual(case,{})

 def test_new_assignment_above_final_fill_is_rejected_atomically(self):
  from template_review import assign_template_photo
  from calculator_evidence import file_digest
  with tempfile.TemporaryDirectory() as d:
   case,load=self.partial(Path(d));path=load['photos']['height'];case.setdefault('imported_files',[]).append(dict(path=path));before=copy.deepcopy(case)
   with self.assertRaises(ValueError):assign_template_photo(case,1,'full_1',dict(path=path,sha256=file_digest(path)))
   self.assertEqual(case,before)

 def test_non_quarter_fill_requires_and_labels_actual_final_view(self):
  from load_requirements import stage_label
  load=dict(fill_fraction='.4',measurements_confirmed=True)
  self.assertEqual(required_loading_slots(load),{'empty','quarter','half'})
  self.assertEqual(stage_label(load,'half','Half Full'),'Final Load - 40.0% Full')
  self.assertFalse(applicable(load,'three_quarters'))
