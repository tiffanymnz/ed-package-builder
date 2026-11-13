"""Durable same-folder export journal, with repeatable rollback after interruption."""
import hashlib,json,os,shutil,tempfile
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as stream:
  for block in iter(lambda:stream.read(1048576),b''):h.update(block)
 return h.hexdigest()
def sync_file(p):
 with open(p,'r+b') as stream:os.fsync(stream.fileno())
def sync_dir(p):
 if os.name!='nt':
  fd=os.open(p,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
def write_durable(p,data):
 with open(p,'w',encoding='utf-8') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 sync_dir(p.parent)
def rollback(stage):
 entries=json.loads((stage/'journal.json').read_text(encoding='utf-8'))
 for entry in entries:
  name=entry['name'];backup=entry['backup']
  if not name or name in ('.','..') or any(c in name for c in '/\\:') or Path(name).name!=name:raise ValueError('Unsafe recovery destination.')
  target=stage.parent/name
  if target.is_symlink():raise ValueError('Recovery destination is a symbolic link.')
  if backup is not None:
   if not str(backup).isdigit():raise ValueError('Unsafe recovery backup.')
   p=stage/str(backup)
   if p.is_symlink() or digest(p)!=entry['sha256']:raise ValueError('Recovery backup is damaged. Existing exports were preserved.')
 for entry in entries:
  target=stage.parent/entry['name'];backup=entry['backup']
  if backup is None:target.unlink(missing_ok=True)
  else:
   incoming=stage/'restore';shutil.copyfile(stage/str(backup),incoming);sync_file(incoming);os.replace(incoming,target)
 sync_dir(stage.parent)
def _recover_bundles(parent):
 recovered=0
 for stage in sorted(Path(parent).glob('.ed-publish-*')):
  if stage.is_symlink() or not stage.is_dir():continue
  if (stage/'COMMITTED').exists():shutil.rmtree(stage);continue
  if not (stage/'READY').exists():continue
  rollback(stage);shutil.rmtree(stage);recovered+=1
 return recovered

def _publish_bundle(replacements):
 items=[(Path(t).resolve(),Path(s) if s is not None else None) for t,s in replacements]
 if not items:return
 keys=[str(p).casefold() if os.name=='nt' else str(p) for p,_ in items]
 if len(keys)!=len(set(keys)):raise ValueError('Export destinations must be distinct.')
 parent=items[0][0].parent
 if any(t.parent!=parent for t,s in items):raise ValueError('Export files must share one output folder.')
 parent.mkdir(parents=True,exist_ok=True);_recover_bundles(parent)
 for target,_ in items:
  if target.exists() and not target.is_file():raise ValueError('An export destination is not a file: '+str(target))
 stage=Path(tempfile.mkdtemp(prefix='.ed-publish-',dir=parent));ready=False;complete=False
 try:
  entries=[];prepared=[]
  for index,(target,source) in enumerate(items):
   backup=str(index) if target.exists() else None
   if backup is not None:shutil.copyfile(target,stage/backup);sync_file(stage/backup)
   incoming=stage/f'{index}.new' if source is not None else None
   if incoming is not None:shutil.copyfile(source,incoming);sync_file(incoming)
   entries.append(dict(name=target.name,backup=backup,sha256=digest(stage/backup) if backup else None,incoming_sha256=digest(incoming) if incoming is not None else None));prepared.append((target,incoming))
  write_durable(stage/'journal.json',json.dumps(entries));write_durable(stage/'READY','ready');ready=True
  try:
   for target,incoming in prepared:
    if incoming is not None:os.replace(incoming,target)
    else:target.unlink(missing_ok=True)
   sync_dir(parent)
   for entry in entries:
    target=parent/entry['name'];expected=entry['incoming_sha256']
    if (expected is None and target.exists()) or (expected is not None and digest(target)!=expected):raise RuntimeError('An exported file failed verification. The previous files were restored.')
   write_durable(stage/'COMMITTED','committed');complete=True
  except Exception:
   rollback(stage);complete=True;raise
 finally:
  if complete or not ready:shutil.rmtree(stage,ignore_errors=True)

from contextlib import contextmanager
@contextmanager
def folder_lock(parent):
 key=hashlib.sha256(str(Path(parent).resolve()).casefold().encode()).hexdigest()
 directory=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'EDPackageBuilder'/'ExportLocks';directory.mkdir(parents=True,exist_ok=True)
 stream=open(directory/(key+'.lock'),'a+b')
 try:
  stream.seek(0,2)
  if stream.tell()==0:stream.write(b'0');stream.flush()
  stream.seek(0)
  try:
   if os.name=='nt':
    import msvcrt
    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError as exc:raise RuntimeError('Another export is using this folder. Wait for it to finish, then save again.') from exc
  try:yield
  finally:
   stream.seek(0)
   if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
 finally:stream.close()

def publish_bundle(replacements):
 items=list(replacements)
 if not items:return
 parent=Path(items[0][0]).resolve().parent;parent.mkdir(parents=True,exist_ok=True)
 with folder_lock(parent):return _publish_bundle(items)

def recover_bundles(parent):
 if not Path(parent).is_dir():return 0
 with folder_lock(parent):return _recover_bundles(parent)
