"""Read-only verification of dashboard hospital folders against staging manifests."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path

from hospital_management import Management
from patient_split_check import patient_id, IMAGE_EXTENSIONS

ROOT=Path(__file__).resolve().parent


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def main():
    management=Management()
    prior=json.loads((ROOT/'multiseed_outputs/hospital_train_val_latest.json').read_text())
    with (Path(prior['report_directory'])/'manifest.csv').open(newline='',encoding='utf-8') as f:
        source={r['sha256']:r for r in csv.DictReader(f)}
    with management.connection() as db:
        hospitals=[dict(r) for r in db.execute('SELECT id,code,status,wallet FROM hospitals')]
        clients={r['hospital']:dict(r) for r in db.execute('SELECT hospital,delegate,consent,manifest FROM portal_clients')}
    errors=[];reports=[];patient_sets={};hash_sets={}
    for hospital in hospitals:
        identity=hospital['id'];folder=management.state/'hospital_data'/identity
        maps={}
        if not (folder/'patients.csv').exists():errors.append(hospital['code']+': patients.csv missing')
        else:
            with (folder/'patients.csv').open(newline='',encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    if r['relative_path'] in maps:errors.append(hospital['code']+': duplicate CSV path '+r['relative_path'])
                    maps[r['relative_path']]=r['patient_id']
        paths=[];counts={}
        for split in ('train','val'):
            counts[split]={}
            for label in ('NORMAL','PNEUMONIA'):
                directory=folder/split/label
                if not directory.is_dir():errors.append(hospital['code']+': missing '+split+'/'+label)
                items=sorted(p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
                counts[split][label]=len(items);paths.extend(items)
                if not items:errors.append(hospital['code']+': empty class '+split+'/'+label)
        if {p.relative_to(folder).as_posix() for p in paths}!=set(maps):errors.append(hospital['code']+': CSV image inventory mismatch')
        patients=defaultdict(set);hashes=defaultdict(list);matched=Counter();unrecognized=0;split_mismatch=0;id_mismatch=0
        with ThreadPoolExecutor(max_workers=4) as pool:
            for path,digest in zip(paths,pool.map(sha,paths)):
                relative=path.relative_to(folder).as_posix();split,label=Path(relative).parts[:2]
                patient=maps.get(relative)
                if not patient:errors.append(hospital['code']+': patient ID missing '+relative);continue
                inferred,parsed=patient_id(path,split,folder)
                if parsed and patient!=inferred:id_mismatch+=1
                patients[split].add(patient);hashes[digest].append(relative)
                expected=source.get(digest)
                if expected:
                    matched[expected['hospital']]+=1
                    if expected['split']!=split or expected['label']!=label or expected['patient_id']!=patient:split_mismatch+=1
                else:unrecognized+=1
        overlap=patients['train']&patients['val'];duplicates=sum(len(v)>1 for v in hashes.values())
        if overlap or duplicates or unrecognized or split_mismatch or id_mismatch or len(matched)!=1:
            errors.append(hospital['code']+': content/patient/split checks failed')
        patient_sets[hospital['code']]=patients['train']|patients['val'];hash_sets[hospital['code']]=set(hashes)
        client=clients.get(identity,{})
        live={}
        try:
            from blockchain.hospital_directory import Directory
            from blockchain.client_authorization import ClientAuthorization
            live['approved_on_chain']=Directory().membership(hospital['wallet'])['authorized']
            live['delegate_eligible']=bool(client.get('delegate') and ClientAuthorization().eligible(hospital['wallet'],client['delegate']))
        except Exception as exc:live={'error':str(exc)}
        report={'code':hospital['code'],'id':identity,'status':hospital['status'],'counts':counts,'total_images':len(paths),
                'patient_counts':{k:len(v) for k,v in patients.items()},'train_val_patient_overlap':len(overlap),
                'exact_duplicate_groups':duplicates,'verified_content_matches':dict(matched),'unrecognized_images':unrecognized,
                'split_label_patient_mismatches':split_mismatch,'csv_vs_filename_id_mismatches':id_mismatch,
                'client_consent_saved':bool(client.get('consent')),'data_registered':bool(client.get('manifest')),'live_authorization':live}
        reports.append(report);print(json.dumps(report),flush=True)
    cross=[]
    for a,b in combinations(patient_sets,2):
        item={'hospital_a':a,'hospital_b':b,'patient_overlap':len(patient_sets[a]&patient_sets[b]),'exact_image_overlap':len(hash_sets[a]&hash_sets[b])}
        cross.append(item)
        if item['patient_overlap'] or item['exact_image_overlap']:errors.append('Cross-hospital overlap: '+a+'/'+b)
    result={'checked_utc':datetime.now(timezone.utc).isoformat(),'hospitals':reports,'cross_hospital_checks':cross,'errors':errors,
            'passed':not errors,'scope':'Exact copied-content checks and filename-inferred patient checks. No registration, training or data edits.'}
    out=ROOT/'multiseed_outputs/hospital_copy_checks.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as f:f.write('\n'+result['checked_utc']+' Added/ran check_hospital_copied_data.py: read-only dashboard hospital folder inventory, patient CSV coverage, SHA256 against staged split manifest, class/split/patient consistency and cross-hospital overlap; live directory/delegate checks. Result '+str(out)+' passed='+str(result['passed'])+'. No data registration or training.\n')
    print('PASSED:',result['passed'],'ERRORS:',errors)


if __name__=='__main__':main()
