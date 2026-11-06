"""Download public pinned test assets without importing the inference runtime."""
import ast,hashlib,json,sys,urllib.request
from pathlib import Path

def prepare(destination):
    tree=ast.parse(Path(__file__).with_name('load_text_runtime.py').read_text())
    assets=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='ASSETS' for target in node.targets))
    root=Path(destination);root.mkdir(parents=True,exist_ok=True)
    for asset in assets:
        target=root/asset['name'];target.parent.mkdir(parents=True,exist_ok=True)
        valid=lambda:target.is_file() and target.stat().st_size==asset['size'] and hashlib.sha256(target.read_bytes()).hexdigest()==asset['sha256']
        if valid():continue
        part=target.with_suffix(target.suffix+'.partial')
        with urllib.request.urlopen(asset['url'],timeout=60) as source,part.open('wb') as output:
            while block:=source.read(1024*1024):output.write(block)
        if part.stat().st_size!=asset['size'] or hashlib.sha256(part.read_bytes()).hexdigest()!=asset['sha256']:raise RuntimeError('Test model verification failed: '+asset['name'])
        part.replace(target)
    (root/'asset-manifest.json').write_text(json.dumps(assets,indent=2))
if __name__=='__main__':prepare(sys.argv[1])
