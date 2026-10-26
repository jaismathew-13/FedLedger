"""Hospital-scoped workers for portal campaigns; raw images stay in local folders."""
import json
import re
import sqlite3
from pathlib import Path
import time
import functools
import csv

from architecture_io import write_json
import hospital_workers as workers


def checkpoint(job):
    with sqlite3.connect(job['operations_db']) as db:
        joined = db.execute('SELECT joined FROM participation WHERE campaign=? AND hospital=?',
                            (job['campaign'], job['organization'])).fetchone()
        control = db.execute('SELECT control FROM campaigns WHERE id=?', (job['campaign'],)).fetchone()
    if not joined or not joined[0] or not control or control[0] == 'cancel':
        raise RuntimeError('Local participation stopped or campaign cancelled.')
    cancel = Path(job['round_cancel'])
    if cancel.exists():
        raise RuntimeError('Round stopped after timeout or another client failure.')


class Events:
    def __init__(self, job):
        self.job = job
        self.started = time.monotonic()

    def put(self, event):
        checkpoint(self.job)
        from hospital_management import now
        with sqlite3.connect(self.job['operations_db']) as db:
            db.execute('UPDATE hospitals SET heartbeat=? WHERE id=?',(now(),self.job['organization']))
        match = re.search(r'e(\d+)/(\d+) b(\d+)/(\d+) L=([\d.eE+-]+)', event['text'])
        data = {'state': 'training', 'duration_seconds': time.monotonic()-self.started}
        if match:
            epoch, epochs, batch, batches = map(int, match.groups()[:4])
            loss_file=Path(self.job['folder'])/'batch_history.csv'
            new_file=not loss_file.exists()
            with loss_file.open('a',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream)
                if new_file: writer.writerow(['epoch','batch','loss','elapsed_seconds'])
                writer.writerow([epoch,batch,float(match[5]),data['duration_seconds']])
            data.update(epoch=epoch, epochs=epochs, batch=batch, batches=batches,
                        loss=float(match[5]), fraction=((epoch-1)+batch/batches)/epochs)
        write_json(Path(self.job['folder'])/'progress.json', data)



def capture_errors(function):
    @functools.wraps(function)
    def wrapped(job):
        try:
            return function(job)
        except Exception as exc:
            folder=Path(job['folder']);folder.mkdir(parents=True,exist_ok=True)
            write_json(folder/'error.json',{'phase':function.__name__,'error':f'{type(exc).__name__}: {exc}'})
            write_json(folder/'progress.json',{'state':'failed','phase':function.__name__})
            raise
    return wrapped


@capture_errors
def train(job):
    import torch
    import fedprox_core as fl
    workers.PROGRESS_QUEUE = Events(job)
    checkpoint(job)
    manifest = json.loads(Path(job['manifest']).read_text())
    from architecture_io import sha256
    for path, expected in manifest['fingerprints'].items():
        if sha256(path) != expected:
            raise RuntimeError('Local dataset changed since registration.')
    try:
        result = workers.train_hospital(job)
        checkpoint(job)
        from hospital_management import now
        with sqlite3.connect(job['operations_db']) as db:
            db.execute('UPDATE portal_clients SET sync_utc=? WHERE hospital=?',(now(),job['organization']))
        model = fl.build_model(False).to('cuda')
        model.load_state_dict(workers.load_state(Path(job['folder'])/'local_model.pt'))
        metrics = workers._metrics(model, manifest['val'], fl, 'Local validation', 0)
        del model
        torch.cuda.empty_cache()
        write_json(Path(job['folder'])/'local_validation.json', metrics)
        write_json(Path(job['folder'])/'progress.json', {'state': 'completed', 'fraction': 1,
            'local_validation': metrics, 'duration_seconds': time.monotonic()-workers.PROGRESS_QUEUE.started})
        return result
    finally:
        workers.PROGRESS_QUEUE = None


@capture_errors
def review(job):
    checkpoint(job)
    return workers.review_at_hospital(job)


@capture_errors
def evaluate(job):
    import torch
    import fedprox_core as fl
    checkpoint(job)
    from architecture_io import LocalIPFS
    ipfs = LocalIPFS(progress_position=-1)
    path = ipfs.fetch(job['global']['cid'], job['global']['sha256'], Path(job['folder'])/'global_for_evaluation.pt')
    model = fl.build_model(False).to('cuda')
    model.load_state_dict(workers.load_state(path))
    pairs = json.loads(Path(job['manifest']).read_text())['val']
    loss, labels, predicted, scores = fl.evaluate(model, workers._loader(pairs, fl), 'cuda')
    metrics = fl.compute_metrics(labels, predicted, scores)
    write_json(Path(job['folder'])/'global_validation.json', metrics)
    del model
    torch.cuda.empty_cache()
    # No filenames, patient IDs or raw images returned to coordination.
    return {'loss': loss, 'labels': labels.tolist(), 'predictions': predicted.tolist(),
            'scores': scores.tolist(), 'metrics': metrics}
