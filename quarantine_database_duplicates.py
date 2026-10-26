"""Quarantine verified byte-identical copies while preserving train/val/test."""
from collections import defaultdict, Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'database'
AUDIT=ROOT/'multiseed_outputs/database_duplicates'
PROTECTED={'train','val','test'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    report=ROOT/'multiseed_outputs/database_duplicate_cleanup'/stamp
    archive=ROOT/'archive/database_duplicate_quarantine'/stamp
    report.mkdir(parents=True);archive.mkdir(parents=True)
    entries=json.loads((AUDIT/'fingerprints.json').read_text())
    protected={};moves=[]
    for entry in entries:
        paths=sorted(entry['paths'])
        keep=[p for p in paths if Path(p).parts[0] in PROTECTED]
        for path in keep:protected[path]=entry['file_sha256']
        retained=keep or paths[:1]
        for path in paths:
            if path not in retained:
                assert Path(path).parts[0] not in PROTECTED
                moves.append({'path':path,'sha256':entry['file_sha256'],'retained_reference':retained[0]})
    expected={p for entry in entries for p in entry['paths']}
    extensions={'.jpg','.jpeg','.png','.bmp','.tif','.tiff','.webp'}
    actual={p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file() and p.suffix.lower() in extensions}
    if actual!=expected:raise RuntimeError('Image inventory changed since audit. Re-audit before cleanup.')
    # Verify paths stay in the named workspace and no destination overwrites occur.
    source_root=SOURCE.resolve();archive_root=archive.resolve()
    for move in moves:
        source=SOURCE/move['path'];target=archive/move['path']
        if source.resolve()!=source.absolute() or not source.resolve().is_relative_to(source_root):
            raise RuntimeError('Source aliases another location: '+str(source))
        if not target.resolve().is_relative_to(archive_root) or target.exists():raise RuntimeError('Invalid archive destination')
    before={p:((SOURCE/p).stat().st_size,(SOURCE/p).stat().st_mtime_ns) for p in protected}
    (report/'plan.json').write_text(json.dumps({'protected':sorted(PROTECTED),'archive':str(archive),'moves':moves},indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:
        f.write('\n'+datetime.now(timezone.utc).isoformat()+' Command quarantine_database_duplicates.py: user-authorized removal via recoverable quarantine, using verified prior SHA256 groups; protected database/train,val,test. Plan '+str(report/'plan.json')+'. Perceptual-only candidates retained.\n')
    # Preflight every duplicate and its retained reference before moving any image.
    verified=set()
    for i,move in enumerate(moves,1):
        for path in (move['path'],move['retained_reference']):
            if path not in verified:
                if digest(SOURCE/path)!=move['sha256']:raise RuntimeError('Content changed: '+path)
                verified.add(path)
        if i%2000==0:print('Verified planned moves',i,'/',len(moves),flush=True)
    completed=[]
    with (report/'moved_files.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['path','sha256','retained_reference','archive_path']);writer.writeheader()
        for move in moves:
            source=SOURCE/move['path'];target=archive/move['path'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(source),str(target))
            if digest(target)!=move['sha256']:raise RuntimeError('Archive verification failed: '+str(target))
            writer.writerow(dict(move,archive_path=str(target)));f.flush();completed.append(move)
    for i,(path,sha) in enumerate(protected.items(),1):
        file=SOURCE/path
        if (file.stat().st_size,file.stat().st_mtime_ns)!=before[path] or digest(file)!=sha:
            raise RuntimeError('Protected image differs from audit: '+path)
        if i%2000==0:print('Verified protected images',i,'/',len(protected),flush=True)
    remaining=defaultdict(list)
    moved={m['path'] for m in completed}
    for entry in entries:
        remaining[entry['file_sha256']]=[p for p in entry['paths'] if p not in moved]
    unprotected_duplicate_groups=sum(len(paths)>1 and any(Path(p).parts[0] not in PROTECTED for p in paths) for paths in remaining.values())
    assert unprotected_duplicate_groups==0
    result={'completed_utc':datetime.now(timezone.utc).isoformat(),'archive':str(archive),'report':str(report),
            'moved_images':len(completed),'moved_by_folder':dict(Counter(Path(m['path']).parts[0] for m in completed)),
            'protected_images_verified':len(protected),'remaining_images':sum(map(len,remaining.values())),
            'remaining_counts':dict(Counter(Path(p).parts[0] for paths in remaining.values() for p in paths)),
            'remaining_exact_duplicate_groups':sum(len(paths)>1 for paths in remaining.values()),
            'unprotected_exact_duplicate_groups':unprotected_duplicate_groups,
            'note':'Remaining exact duplication is confined to protected train/val/test. Perceptual candidates remain pending review.'}
    for target in (report/'summary.json',AUDIT/'cleanup_summary.json'):
        target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    (archive/'README.txt').write_text('Recoverable exact duplicates. Restore using moved_files.csv in '+str(report)+'\nNo dataset images permanently deleted.\n',encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Quarantine completed: '+json.dumps(result)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
