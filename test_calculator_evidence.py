"""Synthetic fixtures exercise evidence handling, not website authenticity."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from PIL import Image, ImageDraw
from docx import Document
from ed_builder import make_example, build
from calculator_evidence import URL, file_digest, measurement_signature, screenshot_status

class CalculatorEvidenceTests(unittest.TestCase):
    def fixture(self, folder):
        case = make_example(folder/'case.json'); case['loads'] = case['loads'][:1]
        load = case['loads'][0]
        path = folder/'fixture.png'
        image = Image.new('RGB', (800, 400), '#eff5f7')
        ImageDraw.Draw(image).text((20, 20), 'TEST FIXTURE - NOT A WEBSITE SCREENSHOT', fill='black')
        image.save(path)
        load['calculator_evidence'] = dict(path=str(path), source_url=URL, user_confirmed=True,
            measurement_signature=measurement_signature(load), sha256=file_digest(path))
        return case, load, path

    def test_missing_evidence_has_no_manufactured_calculator(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); case, load, _ = self.fixture(folder)
            load.pop('calculator_evidence')
            result = build(case, folder/'draft.docx')
            self.assertIsNotNone(result['loads'][0]['calculator_issue'])
            doc = Document(folder/'draft.docx')
            self.assertEqual(len(doc.inline_shapes), 0)
            self.assertIn('DRAFT ONLY', doc.tables[0].cell(0, 0).text)

    def test_selected_image_is_embedded_without_redrawing(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); case, load, path = self.fixture(folder)
            result = build(case, folder/'draft.docx')
            self.assertIsNone(result['loads'][0]['calculator_issue'])
            with ZipFile(folder/'draft.docx') as package:
                media = [package.read(name) for name in package.namelist() if name.startswith('word/media/')]
            self.assertIn(path.read_bytes(), media)

    def test_measurement_change_invalidates_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            case, load, _ = self.fixture(Path(directory))
            load['width_ft'] = 7
            self.assertIn('Measurements changed', screenshot_status(load)[1])

    def test_numeric_equivalence_does_not_invalidate_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            case, load, _ = self.fixture(Path(directory))
            load['width_ft'] = '6.0'
            self.assertIsNone(screenshot_status(load)[1])

    def test_changed_image_or_unconfirmed_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            case, load, path = self.fixture(Path(directory))
            load['calculator_evidence']['user_confirmed'] = False
            self.assertIsNotNone(screenshot_status(load)[1])
            load['calculator_evidence']['user_confirmed'] = True
            Image.new('RGB', (800, 400), 'red').save(path)
            self.assertIn('file changed', screenshot_status(load)[1])

if __name__ == '__main__': unittest.main()
