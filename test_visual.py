import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from visual_intake import classify_records, export


class TestVisual(unittest.TestCase):
    def test_synthetic_images_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            photo = base / "synthetic.png"
            Image.new("RGB", (80, 60), "blue").save(photo)
            broken = base / "broken.jpg"
            broken.write_bytes(b"not an image")

            records = [
                {"path": str(photo)},
                {"path": str(broken)},
                {"path": str(base / "missing.jpg")},
            ]
            rows = classify_records(records)
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(
                rows[0]["candidate"], "Unreadable image"
            )
            self.assertEqual(
                rows[1]["candidate"], "Unreadable image"
            )

            output = base / "output"
            exported, counts = export(
                {"imported_files": records}, output
            )
            self.assertEqual(len(exported), 2)
            self.assertEqual(sum(counts.values()), 2)

            summary = json.loads(
                (output / "Visual_Review_Summary.json").read_text()
            )
            self.assertEqual(summary["verified_assignments"], 0)
            self.assertTrue(
                (output / "Visual_Review_Candidates.csv").is_file()
            )


if __name__ == "__main__":
    unittest.main()
