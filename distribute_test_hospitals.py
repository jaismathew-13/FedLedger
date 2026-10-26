"""Copy training images into unequal, label-skewed, patient-grouped hospitals."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import shutil

from patient_split_check import patient_id, IMAGE_EXTENSIONS

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'database'
SEED=42
SHARES=(.5,.3,.2)
NAMES=('hospital1','hospital2','hospital3')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-existing',action='store_true',help='Preserve existing staging folders in archive before rebuilding.')
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=ROOT/'multiseed_outputs/hospital_distribution'/stamp;out.mkdir(parents=True)
    destinations=[DATA/name for name in NAMES]
    if any(path.exists() for path in destinations) and not args.archive_existing:raise RuntimeError('A destination exists; use --archive-existing for a recoverable rebuild.')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Command distribute_test_hospitals.py: user-authorized non-IID revision BEFORE training. Seed42 unchanged; approximate50/30/20 sizes, pneumonia targets30%/65%/remaining class mass, patient-wise grouping, byte dedup before COPYING. Archive previous balanced staging copies; source train/val/test unchanged.\n')
    rows=[];duplicates=[];seen={};unparsed=[]
    for label in ('NORMAL','PNEUMONIA'):
        for path in sorted((DATA/'train'/label).rglob('*')):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:continue
            digest=sha(path);patient,parsed=patient_id(path,'train',DATA)
            if not parsed:unparsed.append(str(path))
            record={'source':str(path),'label':label,'patient_id':patient,'sha256':digest,'size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
            if digest in seen:
                if seen[digest]['label']!=label:raise RuntimeError('Exact duplicate has conflicting labels.')
                duplicates.append({'source':str(path),'retained_source':seen[digest]['source'],'sha256':digest})
            else:seen[digest]=record;rows.append(record)
    if unparsed:raise RuntimeError('Unparsed patient IDs require a reviewed mapping before patient-wise distribution.')
    groups=defaultdict(list)
    for row in rows:groups[row['patient_id']].append(row)
    totals=Counter(row['label'] for row in rows)
    # Register feasible class targets before assigning any patients.
    size_targets=[int(len(rows)*share) for share in SHARES]
    for i in sorted(range(3),key=lambda i:-(len(rows)*SHARES[i]-size_targets[i]))[:len(rows)-sum(size_targets)]:size_targets[i]+=1
    pneumonia_targets=[round(size_targets[0]*.30),round(size_targets[1]*.65),0]
    pneumonia_targets[2]=totals['PNEUMONIA']-sum(pneumonia_targets[:2])
    targets=[{'NORMAL':size_targets[i]-pneumonia_targets[i],'PNEUMONIA':pneumonia_targets[i]} for i in range(3)]
    if any(value<=0 for target in targets for value in target.values()):raise RuntimeError('Requested label skew is infeasible for available source data.')
    (out/'registered_partition.json').write_text(json.dumps({'seed':SEED,'target_size_shares':SHARES,'class_targets':targets,'reason':'User requested unequal disease proportions; new staging partition before any campaign training.'},indent=2),encoding='utf-8')
    rng=random.Random(SEED);ordered=list(groups.items());rng.shuffle(ordered);ordered.sort(key=lambda item:-len(item[1]))
    assigned=[[] for _ in NAMES];counts=[Counter() for _ in NAMES]
    for patient,images in ordered:
        composition=Counter(row['label'] for row in images)
        scores=[sum(counts[i][label]/targets[i][label]*count for label,count in composition.items()) for i in range(3)]
        minimum=min(scores);index=rng.choice([i for i,v in enumerate(scores) if abs(v-minimum)<1e-12])
        assigned[index].extend(images);counts[index].update(composition)
    patient_sets=[{r['patient_id'] for r in group} for group in assigned]
    assert all(not patient_sets[a]&patient_sets[b] for a,b in combinations(range(3),2))
    previous_archive=None
    if any(path.exists() for path in destinations):
        previous_archive=ROOT/'archive/hospital_distributions'/('balanced_'+stamp)
        previous_archive.mkdir(parents=True)
        for folder in destinations:
            if not folder.exists():continue
            resolved=folder.resolve()
            if resolved!=folder.absolute() or resolved.parent!=DATA.resolve() or resolved.name not in NAMES:raise RuntimeError('Unexpected staging folder path')
            target=previous_archive/folder.name
            if not target.resolve().is_relative_to((ROOT/'archive/hospital_distributions').resolve()) or target.exists():raise RuntimeError('Unexpected archive target')
            shutil.move(str(folder),str(target))
        old_summary=ROOT/'multiseed_outputs/hospital_distribution_latest.json'
        if old_summary.exists():shutil.copy2(old_summary,previous_archive/'previous_summary.json')
    # Record existing overlap with held-out source folders; do not alter those files.
    overlaps={}
    for split in ('val','test'):
        ids={patient_id(p,split,DATA)[0] for p in (DATA/split).rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS}
        overlaps[split]=len(set(groups)&ids)
    mapping=[];stats=[]
    (out/'plan.json').write_text(json.dumps({'seed':SEED,'shares':SHARES,'class_targets':targets,'source':'database/train','assignments':[[dict(r) for r in group] for group in assigned]},indent=2),encoding='utf-8')
    for index,group in enumerate(assigned):
        folder=destinations[index]
        for label in ('NORMAL','PNEUMONIA'):(folder/label).mkdir(parents=True,exist_ok=True)
        with (folder/'patients.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['relative_path','patient_id'])
            for row in group:
                source=Path(row['source']);target=folder/row['label']/source.name
                if target.exists():raise RuntimeError('Filename collision: '+str(target))
                shutil.copy2(source,target)
                if sha(target)!=row['sha256']:raise RuntimeError('Copied content mismatch')
                writer.writerow([target.relative_to(folder).as_posix(),row['patient_id']])
                mapping.append({'hospital':NAMES[index],'source':str(source),'destination':str(target),'label':row['label'],'patient_id':row['patient_id'],'sha256':row['sha256']})
        stats.append({'hospital':NAMES[index],'images':len(group),'patients':len(patient_sets[index]),'NORMAL':counts[index]['NORMAL'],'PNEUMONIA':counts[index]['PNEUMONIA'],'pneumonia_fraction':counts[index]['PNEUMONIA']/len(group)})
        print(stats[-1],flush=True)
        (folder/'README.txt').write_text('Non-IID training-pool copy for prototype test run: unequal sizes AND disease proportions. Patient-grouped across hospitals; not an independent test dataset. Before portal training, create separate train/val patients in the assigned hospital UUID folder. Manifest: '+str(out)+'\n',encoding='utf-8')
    with (out/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(mapping[0]));writer.writeheader();writer.writerows(mapping)
    (out/'excluded_exact_copies.json').write_text(json.dumps(duplicates,indent=2),encoding='utf-8')
    for row in rows:
        file=Path(row['source']);assert (file.stat().st_size,file.stat().st_mtime_ns)==(row['size'],row['mtime_ns'])
    result={'created_utc':datetime.now(timezone.utc).isoformat(),'seed':SEED,'target_shares':SHARES,'target_class_counts':targets,'partition_type':'patient_grouped_quantity_and_label_skew','previous_archive':str(previous_archive) if previous_archive else None,'source':'database/train',
            'copied_images':len(mapping),'exact_copies_not_copied':len(duplicates),'unparsed_images':len(unparsed),
            'hospitals':stats,'cross_hospital_inferred_patient_overlap':0,'cross_hospital_exact_image_overlap':0,
            'source_train_patient_overlap_with_original_evaluation_splits':overlaps,
            'note':'Original train/val/test retained. Their pre-existing patient overlap means they are not independent holdouts for these copies. Inferred filename IDs and exact hashes do not rule out all transformed-image/patient overlap.',
            'report_directory':str(out)}
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (ROOT/'multiseed_outputs/hospital_distribution_latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+datetime.now(timezone.utc).isoformat()+' Hospital copy completed: '+json.dumps(result)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
