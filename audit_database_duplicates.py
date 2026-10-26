"""Read-only content audit of database/; perceptual matches are only candidates."""
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import struct
import time

import imagehash
from PIL import Image, ImageOps, ImageDraw

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'database'
OUT=ROOT/'multiseed_outputs/database_duplicates'
EXT={'.jpg','.jpeg','.png','.bmp','.tif','.tiff','.webp'}


def log(message):
    print(message,flush=True)
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:
        f.write('\n'+datetime.now(timezone.utc).isoformat()+' '+message+'\n')


def file_hash(path):
    value=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def decoded(item):
    digest,paths=item
    try:
        with Image.open(SOURCE/paths[0]) as original:
            image=ImageOps.exif_transpose(original).convert('RGB')
            value=hashlib.sha256(struct.pack('>II',*image.size)+image.tobytes()).hexdigest()
            phash=str(imagehash.phash(image.convert('L')))
            return digest,value,phash,None
    except Exception as exc:return digest,None,None,repr(exc)


def csv_file(name,columns,rows):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def label(path):
    parts={p.lower() for p in Path(path).parts}
    return 'NORMAL' if 'normal' in parts else 'PNEUMONIA' if 'pneumonia' in parts else 'unknown'


def group_report(groups,name):
    rows=[];shared=Counter();within=Counter();duplicate_groups=0;conflicts=[]
    for digest,paths in groups.items():
        if len(paths)<2:continue
        duplicate_groups+=1;by_folder=defaultdict(list)
        for path in paths:by_folder[Path(path).parts[0]].append(path)
        conflict=len({label(p) for p in paths}-{'unknown'})>1
        if conflict:conflicts.append({'hash':digest,'paths':paths})
        for folder,items in by_folder.items():
            if len(items)>1:within[folder]+=1
        for a,b in combinations(sorted(by_folder),2):shared[a,b]+=1
        for path in paths:rows.append({'hash':digest,'folder':Path(path).parts[0],'path':path,'label':label(path),'label_conflict':conflict,'copies_in_group':len(paths)})
    csv_file(name+'.csv',['hash','folder','path','label','label_conflict','copies_in_group'],rows)
    return {'duplicate_groups':duplicate_groups,'within_folder_groups':dict(within),
            'cross_folder_shared_groups':[{'folder_a':a,'folder_b':b,'shared_content_groups':count} for (a,b),count in sorted(shared.items())],
            'label_conflict_groups':len(conflicts),'label_conflict_examples':conflicts[:10]}


def main():
    start=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    log('Command start: python audit_database_duplicates.py; read-only database image-content audit; SHA256, canonical RGB pixels, pHash screening distance<=2. No training/data edits.')
    paths=sorted(p for p in SOURCE.rglob('*') if p.is_file() and p.suffix.lower() in EXT)
    by_bytes=defaultdict(list)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(p,digest) in enumerate(zip(paths,pool.map(file_hash,paths)),1):
            by_bytes[digest].append(p.relative_to(SOURCE).as_posix())
            if i%5000==0:print('File hashes:',i,'/',len(paths),flush=True)
    exact=group_report(by_bytes,'exact_file_duplicates')
    (OUT/'exact_stage.json').write_text(json.dumps(exact,indent=2),encoding='utf-8')
    pixels=defaultdict(list);perceptual=defaultdict(list);errors=[];fingerprints=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(digest,pixel,phash,error) in enumerate(pool.map(decoded,by_bytes.items()),1):
            if error:errors.append({'paths':by_bytes[digest],'error':error});continue
            pixels[pixel].extend(by_bytes[digest]);perceptual[phash].extend(by_bytes[digest])
            fingerprints.append({'file_sha256':digest,'pixel_sha256':pixel,'phash':phash,'paths':by_bytes[digest]})
            if i%2000==0:print('Decoded unique files:',i,'/',len(by_bytes),flush=True)
    pixel_report=group_report(pixels,'identical_pixel_duplicates')
    # BK tree indexes unique 64-bit pHashes; candidate similarity is not proof.
    tree=None;near=[];pair_counts=Counter()
    for key,files in perceptual.items():
        value=int(key,16);matches=[]
        if tree:
            stack=[tree]
            while stack:
                node=stack.pop();distance=(value^node[0]).bit_count()
                if distance<=2:matches.append((node[1],distance))
                stack.extend(child for edge,child in node[2].items() if distance-2<=edge<=distance+2)
        if len(files)>1:matches.append((key,0))
        for other,distance in matches:
            other_files=perceptual[other]
            folders=sorted({Path(p).parts[0] for p in files+other_files})
            if len(folders)<2:continue
            for a,b in combinations(folders,2):pair_counts[a,b]+=1
            near.append({'phash_a':key,'phash_b':other,'distance':distance,'example_a':files[0],
                         'example_b':next((p for p in other_files if Path(p).parts[0]!=Path(files[0]).parts[0]),other_files[0]),
                         'folders':' | '.join(folders),'images_in_hash_a':len(files),'images_in_hash_b':len(other_files)})
        if tree is None:tree=[value,key,{}]
        else:
            node=tree
            while True:
                distance=(value^node[0]).bit_count()
                if distance not in node[2]:node[2][distance]=[value,key,{}];break
                node=node[2][distance]
    csv_file('perceptual_candidates.csv',['phash_a','phash_b','distance','example_a','example_b','folders','images_in_hash_a','images_in_hash_b'],near)
    (OUT/'fingerprints.json').write_text(json.dumps(fingerprints),encoding='utf-8')
    summary={'source':str(SOURCE),'completed_utc':datetime.now(timezone.utc).isoformat(),
             'image_counts':dict(Counter(p.relative_to(SOURCE).parts[0] for p in paths)),
             'total_images':len(paths),'unique_file_contents':len(by_bytes),'unique_decoded_images':len(pixels),
             'exact_file':exact,'identical_pixels':pixel_report,'perceptual_candidate_hash_pairs':len(near),
             'perceptual_note':'pHash distance<=2 flags can include unrelated similar radiographs. Not confirmed copies or patient identity proof.',
             'decode_errors':errors,'duration_seconds':time.monotonic()-start}
    folders=sorted(summary['image_counts'])
    pairs=[]
    for a,b in combinations(folders,2):
        byte_count=sum(any(Path(p).parts[0]==a for p in files) and any(Path(p).parts[0]==b for p in files) for files in by_bytes.values())
        pixel_count=sum(any(Path(p).parts[0]==a for p in files) and any(Path(p).parts[0]==b for p in files) for files in pixels.values())
        pairs.append({'folder_a':a,'folder_b':b,'identical_file_groups':byte_count,'identical_pixel_groups':pixel_count})
    csv_file('folder_comparison.csv',['folder_a','folder_b','identical_file_groups','identical_pixel_groups'],pairs)
    summary['folder_comparisons']=pairs
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    log('Database duplicate audit completed: '+str(len(paths))+' images, '+str(len(by_bytes))+' unique file contents, '+str(len(pixels))+' unique decoded images, '+str(len(errors))+' decoding errors; reports '+str(OUT))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
