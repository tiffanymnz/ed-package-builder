"""Read-only source inventory; does NOT perform image classification."""
import argparse,csv,hashlib,json,zipfile
from collections import Counter
from pathlib import Path
IMAGE={'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}
def audit_archive(path):
    with zipfile.ZipFile(path) as z:
        files=[f for f in z.infolist() if not f.is_dir()]
        names=[f.filename for f in files]
        unsafe=[n for n in names if Path(n).is_absolute() or '..' in Path(n.replace('\\','/')).parts]
        if unsafe: raise ValueError('Unsafe ZIP entries detected')
        types=Counter(Path(n).suffix.lower() or '(none)' for n in names)
        return {'archive':Path(path).name,'total_files':len(files), 'images':sum(v for k,v in types.items() if k in IMAGE),'extensions':dict(types),'unsafe_paths':len(unsafe),'recognition_accuracy':'NOT MEASURED','source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('archive');ap.add_argument('--output');args=ap.parse_args()
    result=audit_archive(args.archive)
    if args.output:Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
