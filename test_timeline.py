import unittest, tempfile
from pathlib import Path
from PIL import Image
from evidence_timeline import make_report

class TestTimeline(unittest.TestCase):
    def test_separate_workorders_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            records = []
            for group in range(7):
                for photo in range(2):
                    path = tmp / f"synthetic_{group}_{photo}.jpg"
                    Image.new("RGB", (80, 60), (group * 30, photo * 100, 40)).save(path)
                    records.append(dict(path=str(path), source="synthetic", work_order=f"test-{group}"))
            rows, summary = make_report(records, tmp / "result")
            self.assertEqual(len(rows), 14)
            self.assertEqual(len(summary["groups"]), 7)
            self.assertTrue(all(g["photos"] == 2 for g in summary["groups"].values()))
            self.assertTrue((tmp / "result" / "Evidence_Timeline.csv").exists())
            self.assertTrue(all(r["sequence_group"] == "Date unavailable" for r in rows))

if __name__ == "__main__":
    unittest.main()
