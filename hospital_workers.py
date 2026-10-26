"""One dedicated process per simulated hospital; images never enter IPFS calls."""
import contextlib
import json
import pickle
from pathlib import Path
from progress_display import ProgressBar

from architecture_io import LocalIPFS, write_json


PROGRESS_QUEUE = None

def initialize_worker(progress_lock=None, progress_queue=None):
    global PROGRESS_QUEUE
    PROGRESS_QUEUE = progress_queue
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required for parallel hospital workers.')
    # Three concurrent workers share the laptop GPU; failure never switches to serial.
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(0.28, 0)


def load_state(path):
    import torch
    import fedprox_core as fl
    saved = torch.load(path, map_location='cpu', weights_only=True)
    state = saved['model_state_dict']
    reference = fl.build_model(False).state_dict()
    if set(state) != set(reference):
        raise ValueError('Checkpoint tensor names differ from ResNet-18.')
    for key, tensor in state.items():
        if not isinstance(tensor, torch.Tensor) or tensor.shape != reference[key].shape or tensor.dtype != reference[key].dtype:
            raise ValueError(f'Invalid tensor schema: {key}')
        if tensor.is_floating_point() and not torch.isfinite(tensor).all().item():
            raise ValueError(f'Nonfinite tensor: {key}')
    return state


def _loader(pairs, fl):
    from torch.utils.data import DataLoader
    return DataLoader(fl.PneumoniaDataset(pairs, fl.eval_transform), batch_size=fl.BATCH_SIZE,
                      shuffle=False, num_workers=0)


def _metrics(model, pairs, fl, label, position):
    with ProgressBar(_loader(pairs, fl), desc=label, unit="batch", position=0, disable=True, leave=False, dynamic_ncols=True) as batches:
        _, labels, predictions, probabilities = fl.evaluate(model, batches, 'cuda')
    return fl.compute_metrics(labels, predictions, probabilities)


def train_hospital(job):
    import torch
    import fedprox_core as fl
    from train_fedprox import Tee
    folder = Path(job['folder'])
    folder.mkdir(parents=True, exist_ok=True)
    import sys
    with (folder/'training.log').open('w', encoding='utf-8') as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)), contextlib.redirect_stderr(Tee(sys.stderr, log_file)):
            try:
                # Each hospital gets a reproducible, distinct per-round random stream.
                fl.set_seed(job['seed'] + (job['round'] - 1) * 3 + job['hospital'])
                ipfs = LocalIPFS(progress_position=-1)
                incoming = ipfs.fetch(job['global']['cid'], job['global']['sha256'], folder/'incoming_global.pt')
                state = load_state(incoming)
                pairs = json.loads(Path(job['manifest']).read_text())['train']
                model = fl.build_model(False).to('cuda')
                dataset = fl.PneumoniaDataset(pairs, fl.train_transform)
                weights = fl.class_weights_for(pairs, 'cuda')
                local, count = fl.client_update(model, state, dataset, 'cuda',
                    job['local_epochs'], fl.LEARNING_RATE, weights, job['mu'], job['name'], progress_position=-1,
                    progress_callback=lambda epoch, epochs, batch, batches, loss: PROGRESS_QUEUE.put(
                        {'hospital': job["hospital"], 'text': f'e{epoch}/{epochs} b{batch}/{batches} L={loss:.4f}'}) if PROGRESS_QUEUE is not None else None)
                path = folder/'local_model.pt'
                torch.save({'model_state_dict': local, 'config': job['model_config'],
                            'round': job['round'], 'hospital_id': job['hospital'],
                            'input_global_sha256': job['global']['sha256']}, path)
                artifact = ipfs.add(path)
                result = dict(artifact, sample_count=count, hospital_id=job['hospital'])
                write_json(folder/'update.json', result)
                del model, state, local, weights
                torch.cuda.empty_cache()
                return result
            except Exception as exc:
                write_json(folder/'error.json', {'phase': 'local_training', 'error': f'{type(exc).__name__}: {exc}'})
                raise


def review_at_hospital(job):
    import torch
    import fedprox_core as fl
    folder = Path(job['folder'])
    folder.mkdir(parents=True, exist_ok=True)
    fl.set_seed(job['seed'])
    pairs = json.loads(Path(job['manifest']).read_text())['val']
    ipfs = LocalIPFS(progress_position=-1)
    incoming = ipfs.fetch(job['global']['cid'], job['global']['sha256'], folder/'review_baseline.pt')
    model = fl.build_model(False).to('cuda')
    model.load_state_dict(load_state(incoming))
    baseline = _metrics(model, pairs, fl, f'H{job["hospital"] + 1} baseline validation', 2 + job['hospital'])
    results = []
    for hospital, update in job['updates'].items():
        hospital = int(hospital)
        if hospital == job['hospital']:
            continue
        evidence = {'reviewer_id': job['hospital'], 'hospital_id': hospital, 'round': job['round'],
                    'cid': update['cid'], 'sha256': update['sha256'], 'baseline': baseline}
        candidate_path = folder/f'peer_{hospital}.pt'
        ipfs.fetch(update['cid'], update['sha256'], candidate_path)
        try:
            candidate_state = load_state(candidate_path)
        except (ValueError, KeyError, TypeError, RuntimeError, EOFError, OSError, pickle.UnpicklingError) as exc:
            evidence.update(valid=False, invalid_reason=f'{type(exc).__name__}: {exc}', candidate=None)
        else:
            model.load_state_dict(candidate_state)
            # Evaluation infrastructure failures abort the run, rather than masquerade as a rejection.
            evidence.update(valid=True, candidate=_metrics(model, pairs, fl, f'H{job["hospital"] + 1} reviewing H{hospital + 1}', 2 + job['hospital']))
            del candidate_state
        path = folder/f'review_of_{hospital}.json'
        write_json(path, evidence)
        results.append({'evidence': evidence, 'path': str(path)})
    del model
    torch.cuda.empty_cache()
    return results
