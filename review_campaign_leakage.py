"""Read-only review of near-duplicate images used by the completed smoke campaign."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import shutil

import imagehash
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from scipy.ndimage import gaussian_filter

from patient_split_check import patient_id

ROOT=Path(__file__).resolve().parent
CAMPAIGN='34c72e51-c98a-4a99-be9a-a540dce32a35'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return '0x'+h.hexdigest()


def similarity(left,right):
    """Local SSIM with 11x11 Gaussian windows, sigma1.5 and unit data range."""
    a,b=left.astype(np.float64),right.astype(np.float64)
    mean_a=gaussian_filter(a,1.5,truncate=3.5)
    mean_b=gaussian_filter(b,1.5,truncate=3.5)
    var_a=gaussian_filter(a*a,1.5,truncate=3.5)-mean_a*mean_a
    var_b=gaussian_filter(b*b,1.5,truncate=3.5)-mean_b*mean_b
    covariance=gaussian_filter(a*b,1.5,truncate=3.5)-mean_a*mean_b
    scores=((2*mean_a*mean_b+.01**2)*(2*covariance+.03**2))/((mean_a**2+mean_b**2+.01**2)*(var_a+var_b+.03**2))
    return float(scores[5:-5,5:-5].mean())


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=ROOT/'multiseed_outputs/campaign_leakage_review'/stamp;out.mkdir(parents=True)
    evidence=ROOT/'multiseed_outputs/portal_campaigns'/CAMPAIGN
    smoke=out/'smoke_evidence';smoke.mkdir()
    archived=[]
    for name in ('history.json','registration.json','selection.json','status.json','result_verification.json'):
        source=evidence/name;shutil.copy2(source,smoke/name);archived.append({'file':name,'sha256':sha(source)})
    (smoke/'manifest.json').write_text(json.dumps({'campaign':CAMPAIGN,'classification':'one_round_workflow_smoke_test_not_independent_evaluation','files':archived},indent=2),encoding='utf-8')
    registration=json.loads((evidence/'registration.json').read_text())
    cache={row['file_sha256']:row for row in json.loads((ROOT/'multiseed_outputs/database_duplicates/fingerprints.json').read_text())}
    rows=[];seen=defaultdict(list);patients=defaultdict(set)
    for hospital in registration['participants']:
        manifest=ROOT/'local_operations/private_manifests'/hospital['id']/(hospital['data_version']+'.json')
        if sha(manifest)!=hospital['manifest_sha256']:raise RuntimeError('Frozen manifest modified')
        data=json.loads(manifest.read_text())
        for split in ('train','val'):
            for path,label in data[split]:
                file=Path(path);pid,parsed=patient_id(file,split,ROOT)
                if not parsed:raise RuntimeError('Cannot infer patient for review')
                rows.append({'path':path,'hospital':hospital['code'],'split':split,'label':int(label),'patient_id':pid})
    def fingerprint(row):
        row=dict(row);row['sha256']=sha(Path(row['path']));cached=cache.get(row['sha256'][2:])
        if cached:row.update(phash=cached['phash'],pixel_sha256=cached['pixel_sha256'])
        else:
            with Image.open(row['path']) as original:
                image=ImageOps.exif_transpose(original).convert('RGB')
                row['phash']=str(imagehash.phash(image.convert('L')))
                import struct
                row['pixel_sha256']=hashlib.sha256(struct.pack('>II',*image.size)+image.tobytes()).hexdigest()
        return row
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Command review_campaign_leakage.py: preserve completed campaign smoke evidence, verify frozen manifests/current image bytes, screen distinct inferred patients with pHash distance<=2; calculate resized256x256 SSIM/correlation/MAE and create review sheets. Screening metrics are not patient-identity proof; no data/policy/training changes.\n')
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(fingerprint,rows))
    print('Fingerprints verified:',len(rows),flush=True)
    for i,row in enumerate(rows):seen[row['sha256']].append(i);patients[row['patient_id']].add((row['hospital'],row['split']))
    # All-pair pHash screening over this small current pool, excluding same-ID pairs.
    values=[int(row['phash'],16) for row in rows];pairs=[]
    for i,a in enumerate(rows):
        for j in range(i):
            b=rows[j]
            if a['patient_id']==b['patient_id']:continue
            distance=(values[i]^values[j]).bit_count()
            if distance<=2:pairs.append((j,i,distance))
    print('Distinct-patient pHash candidate pairs:',len(pairs),flush=True)
    def thumbnail(path):
        with Image.open(path) as image:return np.asarray(ImageOps.exif_transpose(image).convert('L').resize((256,256)),dtype=np.float32)/255
    image_cache={i:thumbnail(rows[i]['path']) for pair in pairs for i in pair[:2]}
    candidates=[]
    for i,j,distance in pairs:
        a,b=rows[i],rows[j];left,right=image_cache[i],image_cache[j]
        corr=float(np.corrcoef(left.ravel(),right.ravel())[0,1])
        if not np.isfinite(corr):corr=0.0
        score=similarity(left,right)
        candidates.append({'index_a':i,'index_b':j,'phash_distance':distance,'ssim':score,'correlation':corr,'mae':float(np.mean(np.abs(left-right))),
                           'path_a':a['path'],'path_b':b['path'],'hospital_a':a['hospital'],'hospital_b':b['hospital'],
                           'split_a':a['split'],'split_b':b['split'],'patient_a':a['patient_id'],'patient_b':b['patient_id'],
                           'label_a':a['label'],'label_b':b['label'],'train_val_crossing':a['split']!=b['split'],
                           'cross_hospital':a['hospital']!=b['hospital'],'high_similarity_flag':score>=.99 and corr>=.995})
    candidates.sort(key=lambda r:(not r['high_similarity_flag'],not r['train_val_crossing'],-r['ssim']))
    if candidates:
        with (out/'candidate_pairs.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(candidates[0]));w.writeheader();w.writerows(candidates)
    sheets=out/'review_sheets';sheets.mkdir()
    # Every distinct-patient candidate is displayed, not just favorable examples.
    for start in range(0,len(candidates),8):
        items=candidates[start:start+8];canvas=Image.new('RGB',(1200,360*len(items)),'white');draw=ImageDraw.Draw(canvas)
        for r,item in enumerate(items):
            for col,key in enumerate(('a','b')):
                row=rows[item['index_'+key]]
                text=f"Pair {start+r+1} | {row['hospital']} {row['split']} | {row['patient_id']} | label={row['label']}"
                draw.text((col*600+8,r*360+5),text,fill='black')
                draw.text((col*600+8,r*360+21),Path(row['path']).name[:85],fill='black')
                with Image.open(row['path']) as image:
                    thumb=ImageOps.contain(image.convert('RGB'),(580,290));canvas.paste(thumb,(col*600+(600-thumb.width)//2,r*360+42))
            draw.text((8,r*360+336),f"pHash={item['phash_distance']} SSIM={item['ssim']:.4f} corr={item['correlation']:.4f} train/val={item['train_val_crossing']}",fill='black')
        canvas.save(sheets/f'pairs_{start+1:04d}_{start+len(items):04d}.jpg')
    summary={'campaign':CAMPAIGN,'completed_utc':datetime.now(timezone.utc).isoformat(),'images':len(rows),
             'exact_duplicate_groups':sum(len(v)>1 for v in seen.values()),
             'inferred_patient_groups_crossing_hospital_or_split':sum(len(v)>1 for v in patients.values()),
             'distinct_patient_perceptual_candidates':len(candidates),'train_val_candidate_pairs':sum(r['train_val_crossing'] for r in candidates),
             'cross_hospital_candidate_pairs':sum(r['cross_hospital'] for r in candidates),
             'high_similarity_flagged_pairs':sum(r['high_similarity_flag'] for r in candidates),
             'high_similarity_train_val_pairs':sum(r['high_similarity_flag'] and r['train_val_crossing'] for r in candidates),
             'label_disagreement_candidates':sum(r['label_a']!=r['label_b'] for r in candidates),
             'criteria':'pHash<=2 candidate screen; high similarity = resized256 SSIM>=.99 and correlation>=.995; visual/source confirmation required',
             'report_directory':str(out),'limitations':'Same-ID candidates excluded because already grouped. Threshold screening can miss rotated/cropped/less-similar copies. No definitive patient/source independence claim.'}
    (out/'fingerprints.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (ROOT/'multiseed_outputs/campaign_leakage_review_latest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Campaign near-copy review calculation completed '+json.dumps(summary)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
