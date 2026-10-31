from pathlib import Path
import tempfile,csv
from PIL import Image
from image_suggestions import candidates
from ground_truth_review import read_rows,evaluate

def test_candidates():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); (root/'thumbnails').mkdir()
        for i in range(3):
            Image.new('RGB',(90,100),(240,240,240) if i==0 else (10,50,80)).save(root/'thumbnails'/f'{i}.png')
        fields=['id','work_order','archive','original_name','original_index','sha256','thumbnail','category','load_number','notes','reviewer','reviewed_at']
        with (root/'labels.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for i in range(3):w.writerow(dict(id=str(i),work_order='1234' if i<2 else '5678',thumbnail=f'thumbnails/{i}.png',category='Unreviewed'))
        report=candidates(root/'labels.csv',root/'suggestions')
        assert report['total']==3
        rows=read_rows(root/'suggestions'/'predictions.csv')
        assert len(rows)==3
        assert not any('2' in r['nearest_images'] for r in rows[:2])
        assert report['human_verified_accuracy'] is None
        print('Passed: sample predictions, per-workorder separation, no fictitious accuracy')
if __name__=='__main__':test_candidates()
