"""Run registered portal rounds from a visible VS Code terminal; never from HTTP."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import contextlib
import json
import multiprocessing
from pathlib import Path
import shutil
import time
import uuid

from eth_account import Account
import numpy as np

from architecture_io import LocalIPFS, sha256, write_json, read_json
from blockchain.client_authorization import ClientAuthorization
from blockchain.protocol_chain import ProtocolChain
from blockchain.registry import receipt
from hospital_management import Management, now
from portal_workflow import Workflow
from progress_display import ProgressBar
from train_fedprox import training_guard, record
import hospital_workers
import portal_workers
from peer_policy import decide_update, aggregation_weights

ROOT = Path(__file__).resolve().parent
BASE_RUN = ROOT/'architecture_outputs/run_20261020T093433_860908Z'


class Cancelled(RuntimeError):
    pass


def run_campaign(workflow, identity, *, executor=None, functions=None, chain_factory=ProtocolChain,
                 transport_factory=LocalIPFS, state_loader=hospital_workers.load_state):
    import torch
    import fedprox_core as fl
    torch.set_num_threads(2)
    folder = workflow.campaign_folder(identity)
    registered = read_json((folder/'registration.json'))
    with workflow.management.connection() as db:
        row = db.execute('SELECT document FROM campaigns WHERE id=?', (identity,)).fetchone()
        if not row or json.loads(row['document']) != registered:
            raise ValueError('Registration differs from administrator-approved snapshot.')
    for name,digest in registered.get('source_sha256',{}).items():
        if sha256(ROOT/name)!=digest:
            raise ValueError('Execution source changed after registration; register a new campaign or document a runtime correction.')
    output = folder/'execution'
    output.mkdir(exist_ok=True)
    status_path = folder/'status.json'
    old = read_json(status_path) if status_path.exists() else {}
    if old.get('state') == 'completed':
        raise ValueError('Campaign already completed; no duplicate execution permitted.')
    if old.get('state') in ('failed','cancelled'):
        write_json(folder/'attempt_history'/(str(uuid.uuid4())+'.json'),old)
    status = dict(old, state='running', error=None, updated_utc=now())
    def save(**values):
        status.update(values, updated_utc=now()); write_json(status_path, status)
    def control():
        with workflow.management.connection() as db:
            value = db.execute('SELECT control FROM campaigns WHERE id=?', (identity,)).fetchone()
            participants = list(db.execute('SELECT joined FROM participation WHERE campaign=?', (identity,)))
        if not value or value[0] == 'cancel':
            raise Cancelled('Campaign cancelled; historical submissions preserved.')
        if not participants or not all(row[0] for row in participants):
            raise RuntimeError('A hospital has stopped participation. Retry only after all clients rejoin.')
        return value[0]
    def boundary(phase):
        save(phase=phase)
        while control() == 'pause':
            save(state='paused')
            time.sleep(1)
        save(state='running')
    boundary('initialization')
    private_manifests, signers, delegates = [], {}, []
    # Check immutable configuration, delegation and data before transactions/training.
    authorization = ClientAuthorization() if functions is None else None
    for participant in registered['participants']:
        with workflow.management.connection() as db:
            client = db.execute('SELECT * FROM portal_clients WHERE hospital=?', (participant['id'],)).fetchone()
            hospital = db.execute('SELECT * FROM hospitals WHERE id=?', (participant['id'],)).fetchone()
        if not hospital or hospital['status'] != 'approved' or not client:
            raise ValueError('Participant no longer approved.')
        if authorization and not authorization.eligible(participant['owner'], participant['delegate']):
            raise ValueError('Client delegation no longer eligible.')
        manifest = Path(client['manifest'])
        if sha256(manifest) != participant['manifest_sha256']:
            raise ValueError('Hospital changed data configuration; register a new campaign.')
        data = json.loads(manifest.read_text())
        for path, digest in data['fingerprints'].items():
            if sha256(path) != digest:
                raise ValueError('Registered data changed; new campaign registration required.')
        account = Account.from_key((workflow.state/'agents'/participant['id']/'client.key').read_text())
        if account.address != participant['delegate']:
            raise ValueError('Local client key differs from delegated signer.')
        signers[account.address] = account; delegates.append(account.address); private_manifests.append(manifest)
    transport = transport_factory(progress_position=-1)
    chain = chain_factory(hospital_accounts=delegates, hospital_signers=signers)
    config = registered['configuration']
    if (config['id'], config['local_epochs'], config['mu'], config['seed']) != ('registered_fedprox_v1', 3, 0.01, 42):
        raise ValueError('Unapproved scientific parameters.')
    model_config = json.loads((BASE_RUN/'run_config.json').read_text())
    model_config = {key: model_config[key] for key in ('architecture','algorithm','class_mapping','preprocessing','selection_rule')}
    run_id = sha256(folder/'registration.json')
    policy_hash = '0x'+__import__('hashlib').sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    def global_at(number):
        try:
            return chain.global_model(run_id, number)
        except RuntimeError as exc:
            if 'No published global' not in str(exc):
                raise
            return None
    registry = chain.contract.functions.getRun(run_id).call()
    if not registry[0]:
        write_json(output/'open_run_receipt.json', chain.open_run(run_id, policy_hash))
    else:
        if '0x'+bytes(registry[1]).hex() != policy_hash or list(registry[2]) != delegates:
            raise ValueError('Existing on-chain run differs from registration.')
    for wallet in delegates:
        if chain.client.eth.get_balance(wallet) < chain.client.to_wei(1, 'ether'):
            receipt(chain.client, chain.client.eth.send_transaction({'from': chain.coordinator,
                'to': wallet, 'value': chain.client.to_wei(2, 'ether')}))
    initial = json.loads((BASE_RUN/'initial_global.json').read_text())
    current = global_at(0)
    if current is None:
        transport.fetch(initial['cid'], initial['sha256'], output/'global_round_0000.pt')
        write_json(output/'initial_global_receipt.json', chain.publish_global(run_id, 0, initial, sha256(folder/'registration.json')))
    history_path = output/'history.json'
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    workers = functions or {'train': portal_workers.train, 'review': portal_workers.review, 'evaluate': portal_workers.evaluate}
    def mfs(artifact, name):
        base = ('/project-demos/portal_fixture_' if functions is not None else '/training/portal_')+identity
        transport.post('files/mkdir', params={'arg': base, 'parents': 'true'})
        response = transport.session.post(transport.endpoint+'files/stat', params={'arg': base+'/'+name}, timeout=(10,30))
        if response.ok:
            if response.json()['Hash'] != artifact['cid']:
                raise ValueError('Named IPFS reference differs from existing content.')
        else:
            transport.post('files/cp', params=[('arg','/ipfs/'+artifact['cid']),('arg',base+'/'+name)])
    def recover_receipt(event_name, filters, target):
        if target.exists(): return
        event=getattr(chain.contract.events,event_name)()
        logs=event.get_logs(from_block=0,to_block='latest',argument_filters=filters)
        if len(logs)!=1: raise RuntimeError('Cannot uniquely recover committed transaction receipt.')
        item=chain.client.eth.get_transaction_receipt(logs[0]['transactionHash'])
        if item['status']!=1: raise RuntimeError('Recovered transaction failed.')
        write_json(target,{'status':item['status'],'transaction_hash':item['transactionHash'].to_0x_hex(),
            'block_number':item['blockNumber'],'gas_used':item['gasUsed'],'recovered_from_live_chain':True})
    # Test fixtures may replace the MFS function through their transport implementation.
    try:
        with contextlib.ExitStack() as stack:
            if executor is None:
                pool = stack.enter_context(ProcessPoolExecutor(max_workers=3,
                    mp_context=multiprocessing.get_context('spawn'), initializer=hospital_workers.initialize_worker))
            else:
                pool = stack.enter_context(executor)
            progress = stack.enter_context(ProgressBar(total=registered['rounds'], desc='Portal campaign', unit='round'))
            progress.update(len(history))
            for number in range(len(history)+1, registered['rounds']+1):
                boundary('round_preflight')
                save(round=number)
                if authorization:
                    for item in registered['participants']:
                        if not authorization.eligible(item['owner'], item['delegate']):
                            raise RuntimeError('Hospital suspended or delegate revoked; run stopped at round boundary.')
                start = time.perf_counter()
                rd = folder/f'round_{number:04d}'; rd.mkdir(exist_ok=True)
                cancel = rd/'cancel.request'
                if cancel.exists():
                    cancel.rename(rd/('cancel_'+str(uuid.uuid4())+'.preserved'))
                private_path = rd/'private.json'
                private = read_json(private_path) if private_path.exists() else {'jobs': {}}
                public_path = rd/'public.json'
                public = read_json(public_path) if public_path.exists() else {'round': number,'clients': [],'phase':'created'}
                public['clients'] = public.get('clients') or [{'id':p['id'],'code':p['code'],'state':'waiting'} for p in registered['participants']]
                incoming = chain.global_model(run_id, number-1)
                jobs = []
                for h, participant in enumerate(registered['participants']):
                    previous = private['jobs'].get(str(h))
                    if previous and (Path(previous['folder'])/'local_validation.json').exists():
                        job = previous
                    else:
                        local = workflow.state/'agents'/participant['id']/'campaigns'/identity/f'round_{number:04d}'/str(uuid.uuid4())
                        local.mkdir(parents=True)
                        job = {'folder':str(local),'hospital':h,'organization':participant['id'],
                            'campaign':identity,'operations_db':str(workflow.management.db),'round_cancel':str(cancel),
                            'manifest':str(private_manifests[h]),'global':incoming,'seed':42,'round':number,
                            'local_epochs':3,'mu':0.01,'name':participant['code'],'model_config':model_config}
                        private['jobs'][str(h)] = job
                    jobs.append(job)
                write_json(private_path, private)
                def publish():
                    write_json(public_path, public)
                def parallel(phase, function, selected):
                    boundary(phase); public['phase']=phase; publish()
                    futures = {h:pool.submit(function,job) for h,job in selected}
                    deadline = time.monotonic()+registered['timeout_seconds']
                    finished={}
                    for h,future in futures.items():
                        future.add_done_callback(lambda f,h=h:finished.__setitem__(h,time.monotonic()))
                    while not all(f.done() for f in futures.values()):
                        if any(f.done() and f.exception() is not None for f in futures.values()):
                            cancel.touch()
                        if time.monotonic() > deadline:
                            cancel.touch(); public['phase']='timeout_requested'; publish()
                        try:
                            control()
                        except (Cancelled, RuntimeError):
                            cancel.touch()
                        for h, job in selected:
                            telemetry = Path(job['folder'])/'progress.json'
                            if telemetry.exists() and phase=='local_training':
                                progress_data = read_json(telemetry)
                                public['clients'][h]['progress'] = progress_data
                        publish()
                        details=' | '.join(f"H{h+1} e{c.get('progress',{}).get('epoch','-')} b{c.get('progress',{}).get('batch','-')} L={c.get('progress',{}).get('loss','-')}" for h,c in enumerate(public['clients']))
                        progress.set_postfix_str(f'Round {number}/{registered["rounds"]}: {phase} | {details}')
                        time.sleep(.3)
                    if any(when>deadline for when in finished.values()):
                        cancel.touch();public['phase']='timed_out';publish()
                    if cancel.exists():
                        for h,f in futures.items():
                            public['clients'][h]['state']='failed' if f.exception() is not None else ('timed_out' if public['phase'] in ('timed_out','timeout_requested') else 'stopped')
                        publish()
                        for f in futures.values():
                            try: f.result()
                            except Exception: pass
                        control()
                        raise RuntimeError('Round timed out or a local client stopped; artifacts preserved for retry.')
                    results = {}
                    for h, future in futures.items():
                        try:
                            results[h] = future.result()
                        except Exception as exc:
                            write_json(Path(jobs[h]['folder'])/'coordinator_step_error.json',{'type':type(exc).__name__,'detail':str(exc)})
                            public['clients'][h]['state']='failed'; publish()
                            raise RuntimeError('A hospital step failed. Owner-local artifacts retain details; no private file paths exposed.') from None
                    return results
                pending = [(h,job) for h,job in enumerate(jobs) if not (Path(job['folder'])/'local_validation.json').exists()]
                if pending:
                    parallel('local_training', workers['train'], pending)
                updates = {}
                boundary('update_submission')
                for h,job in enumerate(jobs):
                    local=Path(job['folder']); artifact=json.loads((local/'update.json').read_text())
                    if sha256(local/'local_model.pt') != artifact['sha256']:
                        raise ValueError('Local update differs from saved upload; refusing silent replacement.')
                    existing=chain.update(run_id,number,h)
                    if existing['exists']:
                        if existing['sha256']!=artifact['sha256'] or existing['cid']!=artifact['cid']:
                            raise ValueError('Submitted update is immutable; revised updates require a new round/campaign.')
                    else:
                        write_json(rd/f'update_{h}_receipt.json',chain.submit_update(run_id,number,h,artifact,artifact['sample_count'],incoming['sha256']))
                    recover_receipt('UpdateSubmitted',{'runId':run_id,'round':number,'hospital':h},rd/f'update_{h}_receipt.json')
                    updates[h]=chain.update(run_id,number,h)
                    public['clients'][h].update(state='submitted',update=artifact,
                        submission_receipt=json.loads((rd/f'update_{h}_receipt.json').read_text()),
                        local_validation=json.loads((local/'local_validation.json').read_text()),
                        artifact_bytes=(local/'local_model.pt').stat().st_size)
                    mfs(artifact,f'round_{number:04d}_hospital_{h+1}.pt')
                publish()
                review_jobs=[(h,dict(job,updates=updates)) for h,job in enumerate(jobs)]
                # Review reports are deterministic evaluation of immutable candidate/global artifacts.
                reviews = {}
                pending_reviews = []
                for h, job in review_jobs:
                    reports = [Path(job['folder'])/f'review_of_{other}.json' for other in range(3) if other != h]
                    if all(path.exists() for path in reports):
                        evidence = [read_json(path) for path in reports]
                        if all(item['sha256'] == updates[item['hospital_id']]['sha256'] for item in evidence):
                            reviews[h] = [{'evidence':item,'path':str(path)} for path,item in zip(reports,evidence)]
                            continue
                    pending_reviews.append((h, job))
                if pending_reviews:
                    reviews.update(parallel('peer_validation',workers['review'],pending_reviews))
                by_hospital={h:[] for h in range(3)}
                for reviewer, results in reviews.items():
                    for result in results:
                        evidence=result['evidence']; h=evidence['hospital_id']; valid=evidence['valid']
                        report_path=Path(result['path']); report_hash=sha256(report_path)
                        committed=chain.contract.functions.getReview(run_id,number,h,reviewer).call()
                        if committed[0] and '0x'+bytes(committed[3]).hex()!=report_hash:
                            raise ValueError('Peer report differs from immutable review commitment.')
                        if not committed[0]:
                            counts=lambda m:[m[key] for key in ('tp','fn','tn','fp')]
                            write_json(rd/f'review_{h}_by_{reviewer}_receipt.json',chain.review(run_id,number,h,reviewer,valid,
                                counts(evidence['baseline']) if valid else [0]*4,
                                counts(evidence['candidate']) if valid else [0]*4,report_hash))
                        recover_receipt('PeerReviewed',{'runId':run_id,'round':number,'hospital':h,'reviewer':reviewer},rd/f'review_{h}_by_{reviewer}_receipt.json') if not (rd/f'review_{h}_by_{reviewer}_receipt.json').exists() else None
                        artifact=transport.add(report_path)
                        mfs(artifact,f'round_{number:04d}_review_{h+1}_by_{reviewer+1}.json')
                        public['clients'][h].setdefault('reviews',{})[str(reviewer)]={
                            'reviewer':reviewer,'report_cid':artifact['cid'],'report_sha256':report_hash,
                            'baseline':evidence['baseline'],'candidate':evidence['candidate'],'valid':valid,
                            'receipt':json.loads((rd/f'review_{h}_by_{reviewer}_receipt.json').read_text())}
                        by_hospital[h].append({'reviewer_id':reviewer,
                            'baseline_balanced_accuracy':evidence['baseline']['balanced_accuracy'] if valid else None,
                            'update_balanced_accuracy':evidence['candidate']['balanced_accuracy'] if valid else None})
                decisions=[]
                for h in range(3):
                    decision=decide_update(h,by_hospital[h],[0,1,2])
                    if decision['accepted']!=chain.update(run_id,number,h)['accepted']:
                        raise ValueError('On-chain/off-chain acceptance mismatch.')
                    decision.update(hospital_id=h,sample_count=updates[h]['samples'])
                    decisions.append(decision); public['clients'][h]['decision']=decision
                    public['clients'][h]['state']='accepted' if decision['accepted'] else 'rejected'
                weights=aggregation_weights(decisions)
                public['eligible_updates']=list(weights); public['weights']=weights; publish()
                evidence={'weights':weights,'decisions':decisions,'input_global':incoming}
                write_json(rd/'aggregation.json',evidence)
                public['phase']='aggregation_ready'; publish()
                save(phase='aggregation_ready')
                if registered.get('aggregation_gate', True):
                    approval=rd/'aggregation_approval.json'
                    while not approval.exists():
                        control(); save(state='paused',phase='aggregation_ready')
                        progress.set_postfix_str(f'Round {number}: waiting for administrator aggregation approval')
                        time.sleep(.5)
                    if read_json(approval)['evidence_sha256']!=sha256(rd/'aggregation.json'):
                        raise ValueError('Aggregation approval differs from current evidence.')
                boundary('aggregation_ready')
                published=global_at(number)
                global_path=output/f'global_round_{number:04d}.pt'
                if published is None:
                    if weights:
                        states=[]; masses=[]
                        for h,mass in weights.items():
                            item=chain.update(run_id,number,h)
                            if not item['accepted'] or item['parent_sha256']!=incoming['sha256']:
                                raise ValueError('Unaccepted or stale-parent update.')
                            path=transport.fetch(item['cid'],item['sha256'],rd/f'accepted_{h}.pt')
                            states.append(state_loader(path)); masses.append(mass)
                        state=fl.sample_weighted_aggregate(states,masses)
                        temp=global_path.with_suffix('.pending')
                        torch.save({'model_state_dict':state,'config':model_config,'round':number},temp)
                        temp.replace(global_path)
                    else:
                        transport.fetch(incoming['cid'],incoming['sha256'],global_path)
                    artifact=transport.add(global_path)
                    write_json(rd/'global_receipt.json',chain.publish_global(run_id,number,artifact,sha256(rd/'aggregation.json')))
                    published=chain.global_model(run_id,number)
                else:
                    if published['evidence_hash']!=sha256(rd/'aggregation.json'):
                        raise ValueError('Global aggregation commitment differs from registered decisions.')
                    transport.fetch(published['cid'],published['sha256'],global_path)
                recover_receipt('GlobalPublished',{'runId':run_id,'round':number},rd/'global_receipt.json')
                write_json(rd/'global.json',published); mfs(published,f'round_{number:04d}_global.pt')
                public['global']=published;public['phase']='global_registered';publish()
                evaluations=parallel('global_validation',workers['evaluate'],[(h,dict(job,global_model_version=number,**{'global':published})) for h,job in enumerate(jobs)])
                labels=np.asarray(sum((v['labels'] for v in evaluations.values()),[]))
                predictions=np.asarray(sum((v['predictions'] for v in evaluations.values()),[]))
                scores=np.asarray(sum((v['scores'] for v in evaluations.values()),[]))
                metrics=fl.compute_metrics(labels,predictions,scores)
                loss=sum(v['loss']*len(v['labels']) for v in evaluations.values())/len(labels)
                for h,result in evaluations.items():public['clients'][h]['global_validation']=result['metrics']
                row={'round':number,'validation':metrics,'val_loss':loss,'seconds':time.perf_counter()-start,
                     'accepted':len(weights),'rejected':3-len(weights)}
                history.append(row);write_json(history_path,history)
                best=max(history,key=lambda r:r['validation']['balanced_accuracy'])
                write_json(output/'selection.json',{'best_round':best['round'],'balanced_accuracy':best['validation']['balanced_accuracy']})
                shutil.copyfile(output/f'global_round_{best["round"]:04d}.pt',output/'best_model.pt')
                public.update(phase='completed',metrics=metrics,val_loss=loss,duration_seconds=row['seconds']);publish()
                save(completed_round=number,phase='round_completed',best_round=best['round'])
                progress.update(1)
            save(state='completed',phase='completed',error=None)
        report=ROOT/('multiseed_outputs/portal_workflow_tests' if functions is not None else 'multiseed_outputs/portal_campaigns')/identity
        report.mkdir(parents=True,exist_ok=True)
        for path in (folder/'registration.json',output/'history.json',output/'selection.json',status_path):
            shutil.copyfile(path,report/path.name)
    except BaseException as exc:
        save(state='cancelled' if isinstance(exc,Cancelled) else 'failed',
             error=str(exc),phase=status.get('phase'))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',required=True)
    args=parser.parse_args()
    management=Management();flow=Workflow(management)
    record(f'Visible portal coordinator start: campaign={args.campaign}; registered config; no test data.')
    with training_guard():
        try:
            run_campaign(flow,args.campaign)
        except BaseException as exc:
            status_path=flow.campaign_folder(args.campaign)/'status.json'
            if not status_path.exists() or read_json(status_path).get('state') not in ('failed','cancelled','completed'):
                write_json(status_path,{'state':'failed','phase':'preflight','error':type(exc).__name__+': preflight failed; inspect local terminal','updated_utc':now()})
            record(f'Portal coordinator error: campaign={args.campaign}; {type(exc).__name__}; artifacts preserved.')
            raise
    record(f'Portal coordinator completed: campaign={args.campaign}')


if __name__=='__main__':
    main()
