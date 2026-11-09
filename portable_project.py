"""One portable project archive; case paths are rebased on every open."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from calculator_evidence import file_digest

PREFIX='@edcase/'

def map_data(value,convert):
    if isinstance(value,str):return convert(value)
    if isinstance(value,list):return [map_data(item,convert) for item in value]
    if isinstance(value,dict):return {convert(str(key)):map_data(item,convert) for key,item in value.items()}
    return value

def portable_data(data,root):
    root=Path(root).resolve()
    def convert(value):
        # Windows TEMP may use an 8.3 alias while resolve() returns its long name.
        # Compare resolved filesystem paths, not their original string prefixes.
        try:
            source=Path(value)
            if source.is_absolute():
                source=source.resolve()
                if source==root:return PREFIX
                if source.is_relative_to(root):return PREFIX+source.relative_to(root).as_posix()
        except (OSError,ValueError):pass
        return value
    return map_data(data,convert)

def restored_data(data,root):
    root=Path(root).resolve()
    def convert(value):
        if not value.startswith(PREFIX):return value
        relative=PurePosixPath(value[len(PREFIX):])
        if relative.is_absolute() or '..' in relative.parts or ':' in str(relative) or '\\' in str(relative):raise ValueError('Unsafe project file reference.')
        return str(root.joinpath(*relative.parts))
    return map_data(data,convert)

def project_files(root):
    root=Path(root).resolve()
    return [path for path in root.rglob('*') if path.is_file() and path.relative_to(root).parts[0]!='output' and path.name not in {'case.json','local_photo_sorting.json'} and not path.is_symlink()]

def fingerprint(case,root):
    root=Path(root).resolve()
    files=[(str(path.relative_to(root)),path.stat().st_size,path.stat().st_mtime_ns) for path in project_files(root)]
    cache=Path(root)/'local_photo_sorting.json'
    if cache.is_file():files.append(('local_photo_sorting.json',cache.stat().st_size,cache.stat().st_mtime_ns))
    return hashlib.sha256(json.dumps([case,sorted(files)],sort_keys=True).encode()).hexdigest()

def check_references(case,root):
    root=Path(root).resolve();paths=[]
    for key in ('imported_files','package_documents'):paths.extend(r.get('path','') for r in case.get(key,[]))
    for key in ('before_photos','during_photos','after_photos','financial_pdfs'):paths.extend(case.get(key,[]))
    paths.extend(case.get('property_stage_reviews',{}));paths.extend(case.get('photo_load_assignments',{}))
    paths.extend(case.get('photo_category_examples',{}))
    paths.extend(entry.get('path','') for entry in case.get('template_photo_reviews',{}).values())
    paths.extend(entry.get('path','') for entry in case.get('shared_container_measurements',{}).values())
    paths.extend(case.get('template_geometry_cache',{}))
    paths.extend(case.get('load_identity_cache',{}))
    paths.extend(case.get('load_card_dismissals',{}))
    paths.extend(case.get('load_card_reviews',{}));paths.extend(r.get('path','') for r in case.get('load_card_reviews',{}).values())
    paths.extend(r.get('path','') for r in case.get('load_sequence_anchors',{}).values())
    for rejected in case.get('template_photo_dismissals',{}).values():paths.extend(rejected)
    for load in case.get('loads',[]):
        paths.extend(load.get('photos',{}).values());paths.extend(load.get('extra_measurement_photos',[]));paths.extend(load.get('extra_measurement_slots',{}).values())
        paths.extend([load.get('disposal_photo',''),load.get('evidence_first_10_cyd',''),load.get('calculator_evidence',{}).get('path','')])
    for value in paths:
        if value and not Path(value).resolve().is_relative_to(root):raise ValueError('Project references a file outside its working folder.')

def atomic_copy(source,destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.ed-export-',dir=destination.parent);os.close(fd)
    try:
        shutil.copyfile(source,temporary);os.replace(temporary,destination)
    finally:
        if Path(temporary).exists():Path(temporary).unlink()

def export_project(case,root,destination,cancel=None,progress=None):
    def checkpoint(message):
        if cancel is not None and cancel.is_set():raise InterruptedError('Project saving cancelled. Your previous saved file is unchanged.')
        if progress:progress(message)
    checkpoint('Preparing project...')
    root=Path(root).resolve();destination=Path(destination).resolve()
    if destination==root or destination.is_relative_to(root):raise ValueError('Save the project outside its temporary working folder.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.ed-project-',dir=destination.parent);os.close(fd)
    try:
        files=project_files(root);check_references(case,root)
        manifest={}
        for i,path in enumerate(files,1):
            checkpoint(f'Checking File {i} of {len(files)}')
            manifest[path.relative_to(root).as_posix()]=file_digest(path)
        cache=root/'local_photo_sorting.json'
        cache_bytes=json.dumps(portable_data(json.loads(cache.read_text(encoding='utf-8')),root)).encode() if cache.is_file() else None
        if cache_bytes is not None:manifest['local_photo_sorting.json']=hashlib.sha256(cache_bytes).hexdigest()
        from cor_package import bid_fingerprint
        bid_valid=bool(case.get('bid_review_confirmed') and case.get('bid_confirmation_hash')==bid_fingerprint(case))
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
            archive.writestr('project.json',json.dumps(dict(format='EDCASE',version=1,case=portable_data(case,root),files=manifest,bid_confirmation_valid=bid_valid),indent=2))
            for i,path in enumerate(files,1):
                checkpoint(f'Saving File {i} of {len(files)}')
                archive.write(path,Path('files')/path.relative_to(root))
            if cache_bytes is not None:archive.writestr('files/local_photo_sorting.json',cache_bytes)
        # Verify all bytes in the finished archive before replacing a saved project.
        checkpoint('Verifying Saved Project...')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('The project archive could not be verified.')
            # CRC checks alone cannot detect a source changed after its manifest hash.
            for relative,expected in manifest.items():
                checkpoint('Verifying Saved Source: '+relative)
                actual=hashlib.sha256()
                with archive.open('files/'+relative) as saved:
                    for block in iter(lambda:saved.read(1024*1024),b''):actual.update(block)
                if actual.hexdigest()!=expected:raise ValueError('A source changed while saving. The previous project is unchanged; save again after reviewing the source.')
        checkpoint('Finishing...')
        os.replace(temporary,destination)
    finally:
        if Path(temporary).exists():Path(temporary).unlink()

def import_project(source,root,cancel=None,progress=None):
    def checkpoint(message):
        if cancel is not None and cancel.is_set():raise InterruptedError('Opening cancelled. Your saved project is unchanged.')
        if progress:progress(message)
    checkpoint('Checking the saved project...')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>20000:raise ValueError('Project contains too many files.')
        seen=set();total=0
        for item in entries:
            checkpoint('Checking project contents...')
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or ':' in str(path) or '\\' in str(path) or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe project archive path.')
            reserved={'CON','PRN','AUX','NUL'}|{f'COM{i}' for i in range(1,10)}|{f'LPT{i}' for i in range(1,10)}
            if any(part.rstrip(' .')!=part or part.split('.')[0].upper() in reserved for part in path.parts):raise ValueError('Unsafe Windows project filename.')
            identity=item.filename.casefold()
            if identity in seen:raise ValueError('Duplicate file inside project.')
            seen.add(identity);total+=item.file_size
        if total>20_000_000_000 or total+100_000_000>shutil.disk_usage(root).free:raise ValueError('Not enough free space to open this project.')
        item=archive.getinfo('project.json')
        if item.file_size>30_000_000:raise ValueError('Project details are too large.')
        envelope=json.loads(archive.read(item))
        if envelope.get('format')!='EDCASE' or envelope.get('version')!=1:raise ValueError('Unsupported project format.')
        case=restored_data(envelope['case'],root)
        if not isinstance(case,dict) or not case.get('case_number') or not isinstance(case.get('loads'),list) or not case['loads']:raise ValueError('Project details are incomplete.')
        check_references(case,root)
        manifest=envelope.get('files')
        if not isinstance(manifest,dict):raise ValueError('Project file manifest is missing.')
        for item in entries:
            path=PurePosixPath(item.filename)
            if item.is_dir() or not path.parts or path.parts[0]!='files':continue
            checkpoint('Opening saved source files...')
            if str(PurePosixPath(*path.parts[1:])) not in manifest:raise ValueError('Project contains an unexpected file.')
            relative=PurePosixPath(*path.parts[1:]);target=root.joinpath(*relative.parts);target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as incoming,target.open('wb') as outgoing:shutil.copyfileobj(incoming,outgoing)
        for index,(relative,expected) in enumerate(manifest.items(),1):
            checkpoint(f'Verifying source {index} of {len(manifest)}...')
            candidate=root/relative
            if not candidate.resolve().is_relative_to(root) or not candidate.is_file() or file_digest(candidate)!=expected:raise ValueError('A project file did not match its saved contents.')
        if envelope.get('bid_confirmation_valid'):
            from cor_package import bid_fingerprint
            case['bid_confirmation_hash']=bid_fingerprint(case)
        cache=root/'local_photo_sorting.json'
        if cache.is_file():cache.write_text(json.dumps(restored_data(json.loads(cache.read_text(encoding='utf-8')),root)),encoding='utf-8')
        # Review validity uses original byte hashes; metadata is restored for the
        # quick thumbnail checks when a project moves to another working folder.
        for path,record in case.get('property_stage_reviews',{}).items():
            source=Path(path)
            if source.is_file() and record.get('source_mtime_ns'):
                os.utime(source,ns=(source.stat().st_atime_ns,int(record['source_mtime_ns'])))
        checkpoint('Restoring your progress...')
        (root/'case.json').write_text(json.dumps(case,indent=2),encoding='utf-8')
        return case
