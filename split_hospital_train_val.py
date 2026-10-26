"""Copy patient-disjoint train/validation splits inside the hospital staging folders."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import shutil

ROOT=Path(__file__).resolve().parent
SEED=42
VAL_FRACTION=.20


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=ROOT/'multiseed_outputs/hospital_train_val'/stamp;out.mkdir(parents=True)
    archive=ROOT/'archive/hospital_distributions'/('flat_noniid_'+stamp)
    previous=json.loads((ROOT/'multiseed_outputs/hospital_distribution_latest.json').read_text())
    with (Path(previous['report_directory'])/'manifest.csv').open(newline='',encoding='utf-8') as f:
        expected={str(Path(r['destination'])):r['sha256'] for r in csv.DictReader(f)}
    rng=random.Random(SEED);plans=[]
    for name in ('hospital1','hospital2','hospital3'):
        folder=ROOT/'database'/name
        if any((folder/split).exists() for split in ('train','val')):raise RuntimeError('Train/val folder already exists: '+str(folder))
        with (folder/'patients.csv').open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
        groups=defaultdict(list)
        for row in rows:
            source=folder/row['relative_path']
            if source.resolve()!=source.absolute() or not source.resolve().is_relative_to(folder.resolve()):raise RuntimeError('Invalid image path')
            if str(source) not in expected:raise RuntimeError('Image missing from previous verified manifest')
            groups[row['patient_id']].append(row)
        validation=set()
        for label in ('NORMAL','PNEUMONIA'):
            candidates=[]
            for patient,items in groups.items():
                labels={Path(item['relative_path']).parts[0] for item in items}
                if len(labels)!=1:raise RuntimeError('Mixed-label patient group requires reviewed stratification')
                if label in labels:candidates.append((patient,len(items)))
            if len(candidates)<2:raise RuntimeError('At least two patient groups per class required')
            rng.shuffle(candidates);total=sum(n for _,n in candidates);target=round(total*VAL_FRACTION)
            reachable={0:None};limit=target+max(n for _,n in candidates)
            for patient,count in candidates:
                for old in list(reachable):
                    new=old+count
                    if new<=limit and new not in reachable:reachable[new]=(old,patient)
                if target in reachable:break
            chosen=min((n for n in reachable if 0<n<total),key=lambda n:(abs(n-target),n))
            while chosen:
                chosen,patient=reachable[chosen];validation.add(patient)
        assigned=[]
        for row in rows:
            label=Path(row['relative_path']).parts[0]
            split='val' if row['patient_id'] in validation else 'train'
            assigned.append({'source':str(folder/row['relative_path']),'relative_path':split+'/'+row['relative_path'],
                             'patient_id':row['patient_id'],'split':split,'label':label,'sha256':expected[str(folder/row['relative_path'])]})
        actual={p.relative_to(folder).as_posix() for label in ('NORMAL','PNEUMONIA') for p in (folder/label).rglob('*') if p.is_file()}
        if actual!={row['relative_path'] for row in rows}:raise RuntimeError('Staging inventory differs from patient mapping')
        plans.append((name,folder,assigned))
    (out/'plan.json').write_text(json.dumps({'seed':SEED,'validation_fraction':VAL_FRACTION,'hospitals':[{ 'hospital':name,'assignments':rows} for name,_,rows in plans]},indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Command split_hospital_train_val.py: user requested nested train/val structure. Registered seed42,20% validation per class approximately by whole patients. Copy first, verify SHA256 against previous manifest, archive flat source copies after all hospitals verified; no original train/val/test edits.\n')
    stats=[];all_rows=[];patient_sets=[];hash_sets=[]
    for name,folder,rows in plans:
        for split in ('train','val'):
            for label in ('NORMAL','PNEUMONIA'):(folder/split/label).mkdir(parents=True)
        for row in rows:
            target=folder/row['relative_path'];shutil.copy2(row['source'],target)
            if sha(target)!=row['sha256']:raise RuntimeError('Copied image hash mismatch: '+str(target))
        train_ids={r['patient_id'] for r in rows if r['split']=='train'};val_ids={r['patient_id'] for r in rows if r['split']=='val'}
        assert not train_ids&val_ids
        assert len({r['sha256'] for r in rows})==len(rows)
        patient_sets.append(train_ids|val_ids);hash_sets.append({r['sha256'] for r in rows})
        counts={split:dict(Counter(r['label'] for r in rows if r['split']==split)) for split in ('train','val')}
        stats.append({'hospital':name,'counts':counts,'train_patients':len(train_ids),'val_patients':len(val_ids),'images':len(rows)})
        all_rows.extend(dict(r,hospital=name) for r in rows)
        print(stats[-1],flush=True)
    assert all(not patient_sets[a]&patient_sets[b] and not hash_sets[a]&hash_sets[b] for a,b in combinations(range(3),2))
    # Archive only the verified flat staging copies and old maps; original sources stay in place.
    for name,folder,rows in plans:
        target=archive/name;target.mkdir(parents=True)
        for entry in ('NORMAL','PNEUMONIA','patients.csv','README.txt'):
            source=folder/entry
            if not source.exists():continue
            if source.resolve()!=source.absolute() or source.resolve().parent!=folder.resolve():raise RuntimeError('Unexpected archive source')
            destination=target/entry
            if not destination.resolve().is_relative_to(archive.resolve()) or destination.exists():raise RuntimeError('Unexpected archive target')
            shutil.move(str(source),str(destination))
        with (folder/'patients.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=['relative_path','patient_id']);writer.writeheader()
            writer.writerows({k:r[k] for k in ['relative_path','patient_id']} for r in rows)
        (folder/'README.txt').write_text('Patient-wise train/val staging copy, seed42; approximately80/20 within each class. Non-IID hospital assignment retained. Not an independent final test dataset. Copy these train/,val/ and patients.csv into the correct dashboard-assigned hospital UUID folder before registering local data. Report: '+str(out)+'\n',encoding='utf-8')
    with (out/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(all_rows[0]));writer.writeheader();writer.writerows(all_rows)
    result={'completed_utc':datetime.now(timezone.utc).isoformat(),'seed':SEED,'target_val_fraction':VAL_FRACTION,'hospitals':stats,
            'total_images':len(all_rows),'within_hospital_train_val_patient_overlap':0,'cross_hospital_inferred_patient_overlap':0,
            'cross_hospital_exact_image_overlap':0,'copied_hashes_verified':True,'flat_copy_archive':str(archive),'report_directory':str(out),
            'limitation':'Filename-inferred patient IDs/exact hashes do not exclude every transformed copy; prototype data, no independent evaluation claim.'}
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (ROOT/'multiseed_outputs/hospital_train_val_latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    previous['layout']='train/{NORMAL,PNEUMONIA}, val/{NORMAL,PNEUMONIA}'
    previous['train_val_summary']=str(out/'summary.json')
    (ROOT/'multiseed_outputs/hospital_distribution_latest.json').write_text(json.dumps(previous,indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Hospital train/val split completed: '+json.dumps(result)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
