import tempfile,zipfile,csv
from pathlib import Path
from PIL import Image
from ground_truth_review import sample_archives,read_rows,evaluate
with tempfile.TemporaryDirectory() as temp:
    t=Path(temp);archives=[]
    for k in range(2):
        z=t/f'Workorder_{700+k}_Documents.zip';archives.append(z)
        with zipfile.ZipFile(z,'w') as out:
            for i in range(11):
                im=Image.new('RGB',(32,32),(i*17,99,100));p=t/f'p{i}.png';im.save(p);out.write(p,f'Before Photos/{i}.png')
    rows=sample_archives(archives,t/'test',per_archive=7)
    assert len(rows)==14
    assert len({r['id'] for r in rows})==14
    assert len({r['work_order'] for r in rows})==2
    assert all((t/'test'/r['thumbnail']).is_file() for r in rows)
    rows[0]['category']='Dump receipt'
    from ground_truth_review import save_rows
    save_rows(t/'test'/'labels.csv',rows)
    with (t/'pred.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,['id','predicted_category']);w.writeheader();w.writerow(dict(id=rows[0]['id'],predicted_category='Dump receipt'))
    rep=evaluate(t/'test'/'labels.csv',t/'pred.csv')
    assert rep['evaluated']==1 and rep['accuracy']==1
    print('PASS: reproducible separate-property sampling, thumbnails, human labels, evaluator')
