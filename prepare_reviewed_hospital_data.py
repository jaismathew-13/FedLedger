"""Create a separate v2 copy resolving the reviewed probable image-family overlap."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return '0x'+h.hexdigest()


def main():
    review=json.loads((ROOT/'multiseed_outputs/campaign_leakage_review_latest.json').read_text())
    audit=Path(review['report_directory']);rows=json.loads((audit/'fingerprints.json').read_text())
    destination=ROOT/'database/hospitals_reviewed_v2'
    if destination.exists():raise RuntimeError('Reviewed destination already exists; no overwrite.')
    codes={'SNRSE':'hospital1','ASTER':'hospital2','RGRI':'hospital3'}
    linked={'im:95','im:96'};family='reviewed_image_family:im95_im96'
    out=audit/'corrected_v2';out.mkdir()
    plan=[]
    for row in rows:
        original=Path(row['path']);split=row['split'];patient=row['patient_id']
        is_linked=patient in linked
        if is_linked:
            if row['hospital']!='SNRSE':raise RuntimeError('Unexpected linked-family hospital')
            split='train';patient=family
        label='NORMAL' if row['label']==0 else 'PNEUMONIA'
        relative=Path(split)/label/original.name
        plan.append(dict(row,destination=str(destination/codes[row['hospital']]/relative),new_split=split,new_patient_id=patient,
                         staging_hospital=codes[row['hospital']],relative_path=relative.as_posix(),linked_family=is_linked))
    rules={'reason':'Visual-review probable transformed copy across different filename IDs; conservative image-family linkage, not true patient identity proof.',
           'linked_inferred_ids':sorted(linked),'canonical_group':family,'assignment':'SNRSE/train','seed_changed':False,
           'registered_campaign_unchanged':True,'source_review':str(audit)}
    (out/'registered_correction.json').write_text(json.dumps(rules,indent=2),encoding='utf-8')
    (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    for folder in codes.values():
        for split in ('train','val'):
            for label in ('NORMAL','PNEUMONIA'):(destination/folder/split/label).mkdir(parents=True)
    moved_split=[];patients=defaultdict(lambda:defaultdict(set));hashes=defaultdict(set);counts=defaultdict(Counter)
    for i,row in enumerate(plan,1):
        original=Path(row['path']);target=Path(row['destination'])
        if target.exists():raise RuntimeError('Filename collision')
        shutil.copy2(original,target)
        if sha(target)!=row['sha256']:raise RuntimeError('Copy changed from reviewed source: '+str(original))
        folder=row['staging_hospital'];split=row['new_split']
        patients[folder][split].add(row['new_patient_id']);hashes[folder].add(row['sha256'])
        counts[folder][split+'/'+('NORMAL' if row['label']==0 else 'PNEUMONIA')]+=1
        if split!=row['split']:moved_split.append({'source':row['path'],'destination':row['destination'],'reason':'keep reviewed image family together in training'})
        if i%2000==0:print('Copied verified v2 images',i,'/',len(plan),flush=True)
    for folder in codes.values():
        assert not patients[folder]['train']&patients[folder]['val']
        with (destination/folder/'patients.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['relative_path','patient_id']);w.writeheader()
            w.writerows({'relative_path':r['relative_path'],'patient_id':r['new_patient_id']} for r in plan if r['staging_hospital']==folder)
        (destination/folder/'README.txt').write_text('Reviewed v2 prototype data. Copy train/, val/ and patients.csv together when preparing a NEW campaign. Patient CSV includes a conservative image-family grouping from visual review. Completed smoke data/results are unchanged. No accuracy is established for this revised split. Correction: '+str(out/'registered_correction.json')+'\n',encoding='utf-8')
    assert all(not(hashes[a]&hashes[b]) for a,b in combinations(codes.values(),2))
    assert len({r['sha256'] for r in plan})==len(plan)
    with (out/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(plan[0]));w.writeheader();w.writerows(plan)
    summary={'completed_utc':datetime.now(timezone.utc).isoformat(),'destination':str(destination),'counts':{k:dict(v) for k,v in counts.items()},
             'total_images':len(plan),'split_reassignments':moved_split,'linked_family_images':sum(r['linked_family'] for r in plan),
             'known_reviewed_family_train_val_overlap':0,'exact_duplicate_images':0,'registered_data_modified':False,
             'rules':rules,'note':'Other unconfirmed perceptual candidates retained. Not an independent clinical test set; no revised accuracy evaluated.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (ROOT/'multiseed_outputs/hospital_reviewed_v2_latest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+summary['completed_utc']+' prepare_reviewed_hospital_data.py completed separate copied v2 data; all hashes verified. '+json.dumps(summary)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
