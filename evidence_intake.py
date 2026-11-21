"""Prepare vendor files away from the UI; commit only a completed import."""
import hashlib,os,tempfile,zipfile
from pathlib import Path
from ed_app import ACCEPT,safe

LIMIT=150*1024*1024

def stage_import(files,existing,staging,cancel,progress,limit=LIMIT):
    staging=Path(staging);existing=set(existing);records=[];documents=[];issues=[];duplicates=0
    def checkpoint(message=None):
        if cancel.is_set():raise InterruptedError('Import cancelled. No new files were added.')
        if message:progress(message)
    def store(stream,source,name):
        nonlocal duplicates
        checkpoint('Importing '+name)
        digest=hashlib.sha256();size=0
        fd,temporary=tempfile.mkstemp(prefix='.import-',dir=staging)
        try:
            with os.fdopen(fd,'wb') as output:
                while True:
                    checkpoint();chunk=stream.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>limit:raise ValueError('File exceeds safe import size')
                    digest.update(chunk);output.write(chunk)
            sha=digest.hexdigest()
            if sha in existing:duplicates+=1;return
            path=staging/(sha[:12]+'_'+safe(Path(name).stem)+Path(name).suffix.lower())
            os.replace(temporary,path);existing.add(sha)
            records.append(dict(source=source,path=str(path),sha256=sha,name=name))
            if path.suffix.lower() in ('.pdf','.docx','.txt'):
                from cor_package import document_suggestions
                try:documents.extend(document_suggestions(records[-1]))
                except Exception:
                    documents.append(dict(path=str(path),name=name,role='other',pages='',confirmed=False,amount='',vendor=''))
        finally:
            if Path(temporary).exists():Path(temporary).unlink()
    for raw in files:
        path=Path(raw);checkpoint('Opening '+path.name)
        try:
            if path.suffix.lower()=='.zip':
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        checkpoint()
                        if member.is_dir() or Path(member.filename).suffix.lower() not in ACCEPT:continue
                        if member.file_size>limit:issues.append(f'{path.name}::{member.filename}: too large');continue
                        try:
                            with archive.open(member) as stream:store(stream,f'{path.name}::{member.filename}',Path(member.filename).name)
                        except InterruptedError:raise
                        except Exception as exc:issues.append(f'{path.name}::{member.filename}: {exc}')
            elif path.suffix.lower() in ACCEPT:
                if path.stat().st_size>limit:issues.append(path.name+': too large');continue
                with path.open('rb') as stream:store(stream,str(path),path.name)
        except InterruptedError:raise
        except Exception as exc:issues.append(f'{path.name}: {exc}')
    checkpoint('Preparing document review...')
    return dict(records=records,documents=documents,duplicates=duplicates,issues=issues)


def commit_import(result,destination):
    """Same-volume renames; rollback new files if a commit fails."""
    from calculator_evidence import file_digest
    destination=Path(destination);destination.mkdir(exist_ok=True);moved=[];mapping={}
    try:
        for record in result['records']:
            source=Path(record['path']);target=destination/source.name
            if target.exists():
                if file_digest(target)!=record['sha256']:raise ValueError('An existing import file has conflicting contents.')
            else:os.replace(source,target);moved.append(target)
            mapping[str(source)]=str(target)
    except Exception:
        for path in moved:path.unlink()
        raise
    return [dict(r,path=mapping[r['path']]) for r in result['records']],[dict(d,path=mapping[d['path']]) for d in result['documents']]
