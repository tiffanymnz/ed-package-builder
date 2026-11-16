import copy,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from calculator_evidence import file_digest
from load_text_runtime import MODEL_DIGEST,ASSETS
from load_identity import VERSION,label_number,combine_readings,current_clue,propose_loads,read_load_card,mark_sequence_anchor,explicit_clock,card_candidate
from visual_photo_review import timing_clues

class LoadIdentityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'photo.png';Image.new('RGB',(500,500),'white').save(self.path);self.sha=file_digest(self.path)
  self.case={'loads':[{'photos':{}},{'photos':{}}],'imported_files':[{'path':str(self.path)}]}
 def tearDown(self):self.temp.cleanup()
 def row(self,path,load=None,clock='2026-08-24T14:15:00',source='camera',category='container_photos'):
  return dict(path=path,sha256='sha-'+path,load=load,sequence_time=clock,sequence_source=source,category=category)
 def prepared(self):
  rows=[self.row('a',1,'2026-08-24T14:00:00'),self.row('middle'),self.row('b',1,'2026-08-24T14:30:00')]
  self.case['photo_load_assignments']={r['path']:dict(load=r['load'],sha256=r['sha256']) for r in rows if r['load']}
  self.case['load_sequence_anchors']={f'1:{kind}':dict(path=row['path'],sha256=row['sha256'],sequence_time=row['sequence_time'],sequence_source=row['sequence_source']) for kind,row in [('start',rows[0]),('end',rows[2])]}
  return rows
 def test_label_requires_full_explicit_label_and_valid_integer(self):
  for label in ['Load #2','Load*2','LOAD +2','Load 2']:self.assertEqual(label_number(label),2)
  for label in ['Before Photos_Load 2.jpg','2','Load 2.5','Load #151','Load 0','Loaded 2','Load 2 x 7 ft']:self.assertIsNone(label_number(label))
 def test_disagreement_between_views_is_retained(self):
  self.assertEqual(combine_readings([dict(engine='standard',loads=[2]),dict(engine='florence',loads=[2]),dict(engine='florence',loads=[3])])['status'],'conflict')
 def test_repeated_same_reader_is_not_corroboration(self):
  out=combine_readings([dict(engine='florence',loads=[2]),dict(engine='florence',loads=[2])]);self.assertEqual(out['status'],'single_reader');self.assertIsNone(out['load'])
 def test_agreeing_readers_offer_clue_without_assignment(self):
  result=combine_readings([dict(engine='standard',loads=[2]),dict(engine='florence',loads=[2])]);self.assertEqual(result['load'],2);self.assertEqual(result['status'],'corroborated')
 def test_model_weight_budget_is_below_500_mb(self):self.assertLess(sum(a['size'] for a in ASSETS),500_000_000)
 def test_old_source_or_model_reading_is_ignored(self):
  self.case['load_identity_cache']={str(self.path):dict(sha256=self.sha,model_digest=MODEL_DIGEST,version=VERSION,status='corroborated',load=2)}
  self.assertIsNotNone(current_clue(self.case,str(self.path),self.sha));self.assertIsNone(current_clue(self.case,str(self.path),'changed'))
  self.case['load_identity_cache'][str(self.path)]['model_digest']='old';self.assertIsNone(current_clue(self.case,str(self.path),self.sha))
 def test_reviewed_invoice_is_not_a_load_card(self):
  self.assertFalse(card_candidate(self.path,'INVOICE\nLoad #2'))
  self.case['load_identity_cache']={str(self.path):dict(sha256=self.sha,model_digest=MODEL_DIGEST,version=VERSION,status='corroborated',load=2)}
  self.case['package_documents']=[dict(path=str(self.path),role='invoice',confirmed=True)]
  self.assertIsNone(current_clue(self.case,str(self.path),self.sha))
 def test_only_bounded_matching_clock_interval_proposes_load(self):
  rows=self.prepared();rows+=[self.row('early',clock='2026-08-24T13:59:00'),self.row('late',clock='2026-08-24T14:31:00'),self.row('different-clock',source='photo_text'),self.row('date-only',clock=None)]
  before=copy.deepcopy(self.case);out=propose_loads(self.case,rows)
  self.assertEqual(out['middle']['load'],1)
  for path in ['early','late','different-clock','date-only']:self.assertNotIn(path,out)
  self.assertEqual(self.case,before)
 def test_interleaved_reviewed_other_load_blocks_range(self):
  rows=self.prepared();other=self.row('other',2,'2026-08-24T14:10:00');rows.append(other);self.case['photo_load_assignments']['other']=dict(load=2,sha256=other['sha256'])
  self.assertNotIn('middle',propose_loads(self.case,rows))
 def test_reversed_start_and_end_are_not_reordered_into_valid_range(self):
  rows=self.prepared();rows[0]['sequence_time']='2026-08-24T14:31:00';self.case['load_sequence_anchors']['1:start']['sequence_time']=rows[0]['sequence_time'];self.assertNotIn('middle',propose_loads(self.case,rows))
 def test_changed_clock_reading_requires_new_anchor_review(self):
  rows=self.prepared();rows[0]['sequence_time']='2026-08-24T14:01:00';self.assertNotIn('middle',propose_loads(self.case,rows))
 def test_unmarked_load_membership_does_not_create_time_range(self):
  rows=self.prepared();self.case.pop('load_sequence_anchors');self.assertNotIn('middle',propose_loads(self.case,rows))
 def test_conflicting_card_is_not_overridden_by_time(self):
  rows=self.prepared();self.case['load_identity_cache']={'middle':dict(sha256='sha-middle',version=VERSION,model_digest=MODEL_DIGEST,status='conflict',options=[1,2])}
  self.assertIsNone(propose_loads(self.case,rows)['middle']['load'])
 def test_unseen_load_number_does_not_create_new_load(self):
  r=self.row('card');self.case['load_identity_cache']={'card':dict(sha256=r['sha256'],version=VERSION,model_digest=MODEL_DIGEST,status='corroborated',load=3)}
  out=propose_loads(self.case,[r]);self.assertEqual(out['card']['status'],'new_load');self.assertIsNone(out['card']['load']);self.assertEqual(len(self.case['loads']),2)
 def test_property_photos_do_not_acquire_load_from_time_interval(self):
  rows=self.prepared();rows[1]['category']='property_photos';self.assertNotIn('middle',propose_loads(self.case,rows))
 def test_month_name_dates_and_explicit_times(self):
  clues=timing_clues(self.path,'August 22, 2026 2:15 PM')['clues'];self.assertEqual(clues[0]['date'],'2026-08-22');self.assertEqual(clues[0]['time'],'14:15:00')
  date=timing_clues(self.path,'August 22, 2026')['clues'][0];self.assertIsNone(date['time'])
 def test_ocr_without_am_pm_is_not_a_sequence_clock(self):
  self.assertFalse(explicit_clock(dict(source='Photo Text (Unverified OCR)',value='09/28/2026 3:50',time='03:50:00')))
  self.assertTrue(explicit_clock(dict(source='Photo Text (Unverified OCR)',value='09/28/2026 3:50 PM',time='15:50:00')))
  self.assertTrue(explicit_clock(dict(source='Camera Metadata',time='03:50:00')))
 def test_mark_boundary_checks_source_and_needs_exact_time(self):
  r=dict(path=str(self.path),sha256=self.sha,category='container_photos',sequence_time=None,sequence_source=None)
  with self.assertRaises(ValueError):mark_sequence_anchor(self.case,r,1,'start')
  r.update(sequence_time='2026-08-24T14:00:00',sequence_source='camera');mark_sequence_anchor(self.case,r,1,'start')
  self.assertEqual(self.case['load_sequence_anchors']['1:start']['sha256'],self.sha);self.assertEqual(self.case['loads'][0]['photos'],{})
  self.path.write_bytes(b'changed')
  with self.assertRaises(ValueError):mark_sequence_anchor(self.case,r,1,'end')
 def test_reader_disagreement_and_dimensions_never_become_case_data(self):
  class Fake:
   def read(self,image,task,cancel,max_tokens=224):
    return dict(text='<s>Load #2'+''.join('<loc_'+str(x)+'>' for x in [100,100,800,100,800,300,100,300])+'</s>' if task=='regions' else 'Lood #3',truncated=False)
  with patch('local_reader.read_image',return_value=('Load #2','')):
   result=read_load_card(self.path,'Load #2',threading.Event(),Fake())
  self.assertEqual(result['status'],'conflict');self.assertIsNone(result['load']);self.assertNotIn('dimensions',result);self.assertEqual(self.case['loads'][0]['photos'],{})
