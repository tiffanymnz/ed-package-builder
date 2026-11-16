"""Source freshness, explicit review and category boundaries for scene suggestions."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from calculator_evidence import file_digest
from local_photo_sorter import MODEL_DIGEST, VERSION
from photo_flow import build_photo_rows
from photo_semantics import stage_suggestion
from photo_stage_head import predict_stage
from review_assist import encode_embedding
from visual_photo_review import apply_visual_stage


class SceneStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'after_load_99.jpg')
        Image.new('RGB', (200, 150), 'blue').save(self.path)
        self.row = dict(sha256=file_digest(self.path), model_digest=MODEL_DIGEST,
                        prompt_version=VERSION, prediction=dict(
                            category='property_photos', embedding=encode_embedding(np.ones(512))))
        self.case = dict(loads=[{'photos': {}}], imported_files=[dict(path=self.path)],
                         local_photo_results={self.path: self.row})
    def tearDown(self):
        self.temp.cleanup()
    def test_invalid_and_empty_features_are_rejected(self):
        for vector in (np.zeros(512), np.ones(511), np.full(512, np.nan)):
            with self.assertRaises(ValueError):
                predict_stage(vector)
        result = predict_stage(np.ones(512))
        self.assertTrue(0 <= result['score'] <= 1)
        self.assertFalse(result['verified'])
    def test_scene_head_is_not_called_for_documents_or_containers(self):
        with patch('photo_stage_head.predict_stage', side_effect=AssertionError('Wrong category')):
            for category in ('documents', 'container_photos', 'measurement', 'other'):
                self.assertIsNone(stage_suggestion({}, category, self.row))
    def test_low_confidence_does_not_fall_back_to_generic_text_scores(self):
        with patch('photo_stage_head.predict_stage', return_value=dict(stage=None)):
            self.assertIsNone(stage_suggestion(dict(before=.6, after=.1), 'property_photos', self.row))
    def test_source_checked_scene_suggestion_is_not_an_assignment(self):
        before = copy.deepcopy(self.case)
        with patch('photo_stage_head.predict_stage', return_value=dict(stage='before', head_version='test')):
            rows, _ = build_photo_rows(self.case)
        self.assertEqual(rows[0]['stage_proposal']['stage'], 'before')
        self.assertEqual(rows[0]['stage'], 'review')
        self.assertEqual(self.case, before)
    def test_changed_photo_cannot_reuse_stage_features(self):
        Image.new('RGB', (200, 150), 'red').save(self.path)
        with patch('photo_stage_head.predict_stage', side_effect=AssertionError('Stale features')):
            rows, _ = build_photo_rows(self.case)
        self.assertIsNone(rows[0]['stage_proposal'])
    def test_old_feature_version_waits_for_cache_upgrade(self):
        self.row['prompt_version'] = 'older-analysis'
        with patch('photo_stage_head.predict_stage', side_effect=AssertionError('Old version')):
            rows, _ = build_photo_rows(self.case)
        self.assertIsNone(rows[0]['stage_proposal'])
    def test_confirmed_work_stage_is_preserved_without_a_new_proposal(self):
        apply_visual_stage(self.case, [self.path], 'during', visually_checked=True)
        with patch('photo_stage_head.predict_stage', side_effect=AssertionError('Already reviewed')):
            rows, _ = build_photo_rows(self.case)
        self.assertEqual(rows[0]['stage'], 'during')
        self.assertIsNone(rows[0]['stage_proposal'])
    def test_missing_features_do_not_use_filename_or_semantic_fallback(self):
        self.row['prediction'].pop('embedding')
        with patch('photo_stage_head.predict_stage', side_effect=AssertionError('No features')):
            rows, _ = build_photo_rows(self.case)
        self.assertIsNone(rows[0]['stage_proposal'])


if __name__ == '__main__':
    unittest.main()
