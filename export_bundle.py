"""Publish a package and its sidecars together; roll back a caught write failure.

This is an application-level transaction, not a guarantee against power loss.
Staging is kept beside the outputs to support same-filesystem replacement.
"""
import os,shutil,tempfile
from pathlib import Path

def publish_bundle(replacements):
    items=[(Path(target),Path(source) if source is not None else None) for target,source in replacements]
    if not items:return
    keys=[str(p.resolve()).casefold() if os.name=='nt' else str(p.resolve()) for p,_ in items]
    if len(keys)!=len(set(keys)):raise ValueError('Export destinations must be distinct.')
    for target,_ in items:
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and not target.is_file():raise ValueError('An export destination is not a file: '+str(target))
    stage=Path(tempfile.mkdtemp(prefix='.ed-publish-',dir=items[0][0].parent));prepared=[];committed=[];keep_recovery=False
    try:
        # Finish every copy before touching any previous result.
        for index,(target,source) in enumerate(items):
            backup=stage/f'{index}.previous' if target.exists() else None
            if backup is not None:shutil.copyfile(target,backup)
            incoming=stage/f'{index}.new' if source is not None else None
            if incoming is not None:shutil.copyfile(source,incoming)
            prepared.append((target,incoming,backup))
        try:
            for target,incoming,backup in prepared:
                if incoming is not None:os.replace(incoming,target)
                elif target.exists():target.unlink()
                committed.append((target,backup))
        except Exception:
            failures=[]
            for target,backup in reversed(committed):
                try:
                    if backup is not None:os.replace(backup,target)
                    elif target.exists():target.unlink()
                except OSError:failures.append(str(target))
            if failures:
                keep_recovery=True
                raise RuntimeError('Export failed and some previous files need recovery from '+str(stage)+': '+', '.join(failures))
            raise
    finally:
        if not keep_recovery:shutil.rmtree(stage,ignore_errors=True)
