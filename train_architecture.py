"""Separate full-protocol FedProx experiment: parallel hospitals, IPFS and peers."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import contextlib
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import time
import queue
from concurrent.futures import TimeoutError as FutureTimeout
from progress_display import ProgressBar

from architecture_io import LocalIPFS, sha256, write_json
from architecture_data import prepare_hospitals
from blockchain.protocol_chain import ProtocolChain
from hospital_workers import initialize_worker, train_hospital, review_at_hospital, load_state
from peer_policy import decide_update, aggregation_weights
from train_fedprox import training_guard, Tee, record, save_status

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('TORCH_HOME', str(ROOT/'_torch_cache'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'_mpl_cache'))


def counts(metrics):
    return [metrics[key] for key in ('tp', 'fn', 'tn', 'fp')]


def validate_policy(policy):
    # Policy functions implement this version exactly; edits require a new version.
    expected = {'metric': 'balanced_accuracy', 'reviewers': 'both_other_hospitals',
                'required_approvals': 2, 'allowed_degradation': 0.0,
                'minimum_score_exclusive': 0.5}
    if policy['protocol_version'] != 'peer_fedprox_v1' or policy['num_hospitals'] != 3:
        raise ValueError('Unsupported protocol version or hospital count.')
    if any(policy['peer_validation'].get(key) != value for key, value in expected.items()):
        raise ValueError('Policy parameters differ from implemented v1 decisions.')
    if (policy['seed'], policy['rounds'], policy['local_epochs'], policy['mu']) != (42, 20, 3, 0.01):
        raise ValueError('The registered initial architecture run is seed42/20 rounds/3 epochs/mu0.01.')


def run(output, dataset_root, smoke=False, roster_file=None):
    import torch
    import fedprox_core as fl
    from torch.utils.data import DataLoader
    torch.set_num_threads(2)
    policy = json.loads((ROOT/'architecture_protocol.json').read_text())
    validate_policy(policy)
    # Explicit operational smoke override; registered full-run policy stays on disk unchanged.
    if smoke:
        policy = copy.deepcopy(policy)
        policy["rounds"] = 1
        policy["run_purpose"] = "one_round_integration_smoke_not_final_experiment"
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; no CPU or serial fallback is permitted.')
    if shutil.disk_usage(output).free < 15 * 1024 ** 3:
        raise RuntimeError('At least 15 GiB free space is required for round checkpoints and IPFS pins.')
    ipfs = LocalIPFS(progress_position=-1)
    roster = None
    if roster_file:
        from hospital_management import load_roster
        roster, hospital_accounts, hospital_signers = load_roster(roster_file)
        chain = ProtocolChain(hospital_accounts=hospital_accounts, hospital_signers=hospital_signers)
        # Development-only gas funding; never used on a public network.
        for wallet in hospital_accounts:
            if chain.client.eth.get_balance(wallet) < chain.client.to_wei(1, 'ether'):
                from blockchain.registry import receipt
                receipt(chain.client, chain.client.eth.send_transaction({'from': chain.coordinator,
                    'to': wallet, 'value': chain.client.to_wei(2, 'ether')}))
        write_json(output/'enrollment_roster.json', roster)
    else:
        chain = ProtocolChain()
    manifests, validation_pairs = prepare_hospitals(dataset_root, output, policy['seed'])
    model_config = {'architecture': 'resnet18', 'algorithm': 'FedProx_with_peer_protocol',
        'protocol_version': policy['protocol_version'], 'class_mapping': fl.CLASS_FOLDERS,
        'preprocessing': {'image_size': [224, 224], 'mean': fl.IMAGENET_MEAN, 'std': fl.IMAGENET_STD},
        'selection_rule': 'highest pooled validation balanced accuracy; first round wins ties',
        'seed': policy['seed'], 'mu': policy['mu'], 'rounds': policy['rounds'], 'local_epochs': policy['local_epochs']}
    config = dict(model_config, enrollment_roster_id=roster["id"] if roster else None, policy=policy, started_utc=datetime.now(timezone.utc).isoformat(),
        dataset_root=str(dataset_root.resolve()), execution='three_spawned_parallel_hospital_workers',
        hospital_cuda_memory_fraction=0.28, evaluation_device='cpu_for_pooled_validation',
        local_seed_rule='seed + (round - 1) * 3 + hospital_id', optimizer='Adam',
        learning_rate=fl.LEARNING_RATE, batch_size=fl.BATCH_SIZE, num_workers=0,
        client_profiles=fl.CLIENT_PROFILES, prevalence_noise_std=fl.PREVALENCE_NOISE_STD,
        prevalence_clip=fl.PREVALENCE_CLIP, test_evaluation_requested=False,
        validation_manifest_sha256=[sha256(path) for path in manifests],
        source_sha256={name: sha256(ROOT/name) for name in ('fedprox_core.py', 'peer_policy.py',
            'hospital_workers.py', 'architecture_data.py', 'architecture_io.py', 'train_architecture.py',
            'blockchain/protocol_chain.py', 'blockchain/contracts/FederatedProtocolRegistry.sol')},
        chain_instance_id=chain.instance, contract=chain.contract.address, hospital_accounts=chain.hospitals)
    write_json(output/'run_config.json', config)
    write_json(output/'policy.json', policy)
    run_id = sha256(output/'run_config.json')
    policy_hash = sha256(output/'policy.json')
    write_json(output/'run_identity.json', {'run_id': run_id, 'policy_hash': policy_hash})
    write_json(output/'open_run_receipt.json', chain.open_run(run_id, policy_hash))
    fl.set_seed(policy['seed'])
    initial = fl.build_model(True)
    current_path = output/'global_round_0000.pt'
    torch.save({'model_state_dict': initial.state_dict(), 'config': model_config, 'round': 0}, current_path)
    del initial
    current = ipfs.add(current_path)
    write_json(output/'initial_global.json', current)
    write_json(output/'initial_global_receipt.json', chain.publish_global(run_id, 0, current, sha256(output/'run_config.json')))
    evaluation_model = fl.build_model(False).to('cpu')
    validation_loader = DataLoader(fl.PneumoniaDataset(validation_pairs, fl.eval_transform),
                                   batch_size=fl.BATCH_SIZE, shuffle=False, num_workers=0)
    history, best_score, best_round = [], -1.0, 0
    # A dedicated single-worker pool per hospital keeps process-local data/model ownership.
    progress_lock = multiprocessing.get_context('spawn').RLock()
    with contextlib.ExitStack() as stack:
        manager = stack.enter_context(multiprocessing.Manager())
        progress_queue = manager.Queue()
        progress = stack.enter_context(ProgressBar(total=policy["rounds"], desc="Federated training", unit="round", position=0, dynamic_ncols=True, ascii=True, mininterval=0.5))
        hospital_progress = {}
        def show_progress(phase):
            details = " | ".join(f"H{h + 1} {hospital_progress.get(h, 'waiting')}" for h in range(3))
            progress.set_postfix_str(f"R{round_number}/{policy['rounds']} {phase} | {details}")
        def await_result(future, phase):
            show_progress(phase)
            while True:
                try:
                    result = future.result(timeout=0.25)
                except FutureTimeout:
                    result = None
                while True:
                    try:
                        event = progress_queue.get_nowait()
                        if isinstance(event, dict):
                            hospital_progress[event["hospital"]] = event["text"]
                    except queue.Empty:
                        break
                show_progress(phase)
                if future.done():
                    return future.result()
        pools = [stack.enter_context(ProcessPoolExecutor(max_workers=1,
            mp_context=multiprocessing.get_context('spawn'), initializer=initialize_worker, initargs=(progress_lock, progress_queue))) for _ in range(3)]
        for round_number in range(1, policy['rounds'] + 1):
            if roster_file:
                # Revocations/readiness are enforced at round boundaries for future enrolled runs.
                load_roster(roster_file)
            hospital_progress.clear()
            start = time.perf_counter()
            folder = output/'rounds'/f'round_{round_number:04d}'
            folder.mkdir(parents=True)
            save_status(output, phase='parallel_local_training', current_round=round_number)
            progress.set_postfix_str(f'Round {round_number}: hospital training')
            # Global CID/digest comes from the on-chain version, not a local shortcut.
            current = chain.global_model(run_id, round_number - 1)
            jobs = []
            for hospital in range(3):
                local_folder = output/'hospitals'/f'hospital_{hospital}'/f'round_{round_number:04d}'
                jobs.append(dict(folder=str(local_folder), hospital=hospital, manifest=manifests[hospital],
                    global_model_version=round_number - 1, **{'global': current},
                    seed=policy['seed'], round=round_number, local_epochs=policy['local_epochs'],
                    mu=policy['mu'], name=roster['hospitals'][hospital]['code'] if roster else fl.CLIENT_PROFILES[hospital]['name'], model_config=model_config))
            futures = [pool.submit(train_hospital, job) for pool, job in zip(pools, jobs)]
            updates = {}
            # All futures are submitted before waiting: training is genuinely concurrent.
            for hospital, future in enumerate(futures):
                artifact = await_result(future, "Hospital training + update registration")
                write_json(folder/f'update_{hospital}_receipt.json', chain.submit_update(run_id,
                    round_number, hospital, artifact, artifact['sample_count'], current['sha256']))
                updates[hospital] = chain.update(run_id, round_number, hospital)
                hospital_progress[hospital] = "trained; IPFS + chain OK"
            save_status(output, phase='parallel_peer_validation')
            review_jobs = [dict(job, updates=updates) for job in jobs]
            reviews_futures = [pool.submit(review_at_hospital, job) for pool, job in zip(pools, review_jobs)]
            hospital_progress.clear()
            by_hospital = {hospital: [] for hospital in range(3)}
            for reviewer, future in enumerate(reviews_futures):
                for result in await_result(future, f"Peer validation H{reviewer + 1}"):
                    evidence = result['evidence']
                    hospital = evidence['hospital_id']
                    valid = evidence['valid']
                    baseline = counts(evidence['baseline']) if valid else [0] * 4
                    candidate = counts(evidence['candidate']) if valid else [0] * 4
                    write_json(folder/f'review_{hospital}_by_{reviewer}_receipt.json', chain.review(
                        run_id, round_number, hospital, reviewer, valid, baseline, candidate, sha256(result['path'])))
                    hospital_progress[reviewer] = f"reviewed H{hospital + 1}; attestation OK"
                    by_hospital[hospital].append({'reviewer_id': reviewer,
                        'baseline_balanced_accuracy': evidence['baseline']['balanced_accuracy'] if valid else None,
                        'update_balanced_accuracy': evidence['candidate']['balanced_accuracy'] if valid else None})
            decisions = []
            for hospital in range(3):
                decision = decide_update(hospital, by_hospital[hospital], [0, 1, 2])
                onchain = chain.update(run_id, round_number, hospital)
                if decision['accepted'] != onchain['accepted']:
                    raise RuntimeError('Peer decision differs between off-chain policy and contract.')
                decisions.append(dict(decision, hospital_id=hospital, sample_count=onchain['samples']))
            weights = aggregation_weights(decisions)
            write_json(folder/'decisions.json', decisions)
            write_json(folder/'aggregation.json', {'weights': weights, 'all_rejected': not bool(weights),
                'input_global': current, 'decisions': decisions})
            next_path = output/f'global_round_{round_number:04d}.pt'
            save_status(output, phase='accepted_update_aggregation')
            if weights:
                accepted_states, accepted_masses = [], []
                for hospital, weight in weights.items():
                    progress.set_postfix_str(f'Retrieve accepted update H{hospital + 1}')
                    accepted = chain.update(run_id, round_number, hospital)
                    if not accepted['accepted'] or accepted['parent_sha256'] != current['sha256']:
                        raise RuntimeError('Cannot aggregate unaccepted or stale-parent update.')
                    downloaded = ipfs.fetch(accepted['cid'], accepted['sha256'], folder/'accepted'/f'hospital_{hospital}.pt')
                    accepted_states.append(load_state(downloaded))
                    accepted_masses.append(weight)
                state = fl.sample_weighted_aggregate(accepted_states, accepted_masses, progress_desc=None)
                torch.save({'model_state_dict': state, 'config': model_config, 'round': round_number}, next_path)
                del accepted_states, state
            else:
                # Exact-byte retention also satisfies the contract's digest invariant.
                shutil.copyfile(current_path, next_path)
            progress.set_postfix_str(f"R{round_number}: global IPFS upload + blockchain registration")
            new_global = ipfs.add(next_path)
            write_json(folder/'global.json', new_global)
            write_json(folder/'global_receipt.json', chain.publish_global(run_id, round_number,
                new_global, sha256(folder/'aggregation.json')))
            # Retrieve the published global before selection; next round workers do likewise.
            published = chain.global_model(run_id, round_number)
            retrieved = ipfs.fetch(published['cid'], published['sha256'], folder/'global_retrieved.pt')
            evaluation_model.load_state_dict(load_state(retrieved))
            progress.set_postfix_str('Pooled validation')
            val_loss, y_true, y_pred, probabilities = fl.evaluate(evaluation_model, validation_loader, 'cpu')
            metrics = fl.compute_metrics(y_true, y_pred, probabilities)
            row = dict(round=round_number, accepted_updates=len(weights), all_rejected=not bool(weights),
                       val_loss=val_loss, round_wall_seconds=time.perf_counter() - start,
                       **{'val_' + key: value for key, value in metrics.items()})
            history.append(row)
            with (output/'history.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader(); writer.writerows(history)
            shutil.copyfile(next_path, output/'latest_model.pt')
            if metrics['balanced_accuracy'] > best_score:
                best_score, best_round = metrics['balanced_accuracy'], round_number
                shutil.copyfile(next_path, output/'best_model.pt')
                write_json(output/'validation_metrics.json', metrics)
                write_json(output/'best_global_reference.json', dict(published, selection_round=best_round,
                    checkpoint_sha256=sha256(output/'best_model.pt'), run_id=run_id))
            write_json(output/'selection.json', {'best_round': best_round,
                'best_validation_balanced_accuracy': best_score, 'completed_round': round_number})
            save_status(output, phase='round_completed', completed_round=round_number,
                        best_round=best_round, best_validation_balanced_accuracy=best_score)
            current_path = next_path
            progress.set_postfix_str(f'Accepted {len(weights)}/3; val balanced accuracy={metrics["balanced_accuracy"]:.4f}')
            progress.update(1)
            progress.progress.console.print(
                f"Round {round_number}/{policy['rounds']} completed in {row['round_wall_seconds']:.1f}s | "
                f"accepted={len(weights)}/3 | val loss={val_loss:.4f} | "
                f"accuracy={metrics['accuracy']:.4f} balanced accuracy={metrics['balanced_accuracy']:.4f} | "
                f"F1={metrics['f1']:.4f} AUC={metrics['roc_auc']:.4f} | "
                f"sensitivity={metrics['sensitivity']:.4f} specificity={metrics['specificity']:.4f} | "
                f"best round={best_round} ({best_score:.4f})", markup=False)
    # Evidence copy under the original runbook reporting directory; never a comparison result.
    evidence = ROOT/'multiseed_outputs'/'architecture'/output.name
    evidence.mkdir(parents=True, exist_ok=False)
    for name in ('history.csv', 'run_config.json', 'policy.json', 'selection.json', 'validation_metrics.json', 'best_global_reference.json'):
        shutil.copyfile(output/name, evidence/name)
    print(f'Architecture run completed. Checkpoints: {output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, default=Path(r'D:\dataset_patientsplit'))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--roster-file', type=Path, help='Approved three-hospital local enrollment snapshot for a NEW run.')
    parser.add_argument('--smoke', action='store_true', help='Separate one-round integration smoke; unchanged hospital/epoch/peer rules.')
    args = parser.parse_args()
    output = args.output_dir or ROOT/'architecture_outputs'/datetime.now(timezone.utc).strftime(('smoke_' if args.smoke else 'run_') + '%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    save_status(output, state='running', started_utc=started, pid=os.getpid(), total_rounds=1 if args.smoke else 20, completed_round=0,
                test_evaluation_requested=False, phase='initializing')
    record(f'Full architecture command start: output={output}; no test evaluation; parallel hospitals; protocol v1.')
    import sys
    try:
        with (output/'console.log').open('w', encoding='utf-8') as stream:
            with contextlib.redirect_stdout(Tee(sys.stdout, stream)), contextlib.redirect_stderr(Tee(sys.stderr, stream)):
                run(output, args.dataset_root, smoke=args.smoke, roster_file=args.roster_file)
    except BaseException as exc:
        save_status(output, state='failed', error=f'{type(exc).__name__}: {exc}', ended_utc=datetime.now(timezone.utc).isoformat())
        record(f'Architecture run failed: {exc}; all artifacts preserved in {output}; no silent retry or serial fallback.')
        raise
    else:
        save_status(output, state='completed', phase='completed', ended_utc=datetime.now(timezone.utc).isoformat())
        record(f'Architecture run succeeded: {output}')


if __name__ == '__main__':
    with training_guard():
        main()
