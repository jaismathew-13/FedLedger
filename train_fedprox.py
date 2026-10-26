"""Train one federated ResNet-18 model with FedProx; no method comparison."""
import argparse
import contextlib
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@contextlib.contextmanager
def training_guard():
    """Keep Windows awake and hold an OS lock for this training process."""
    import ctypes
    import msvcrt
    folder = ROOT/'fedprox_outputs'
    folder.mkdir(exist_ok=True)
    with (folder/'.training.lock').open('a+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another FedProx training process holds the training lock.') from exc
        awake = False
        try:
            awake = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            if not awake:
                raise RuntimeError('Could not inhibit automatic sleep for training.')
            yield
        finally:
            if awake:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def save_status(output, **values):
    path = output/'execution.json'
    status = json.loads(path.read_text()) if path.exists() else {}
    status.update(values, updated_utc=stamp())
    temporary = output/'execution.json.tmp'
    temporary.write_text(json.dumps(status, indent=2), encoding='utf-8')
    temporary.replace(path)


class Tee:
    def __init__(self, terminal, file):
        self.terminal, self.file = terminal, file

    def write(self, text):
        self.terminal.write(text)
        self.file.write(text)
        self.flush()
        return len(text)

    def flush(self):
        self.terminal.flush()
        self.file.flush()

    def isatty(self):
        return self.terminal.isatty()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def record(message):
    with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as file:
        file.write(f'\n{stamp()} {message}\n')


def train(args, output):
    import torch
    from torch.utils.data import DataLoader
    import fedprox_core as fl

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; stopping rather than silently training on CPU.')
    device = torch.device('cuda')
    fl.NUM_ROUNDS, fl.LOCAL_EPOCHS = args.rounds, args.local_epochs
    fl.SEED, fl.NUM_WORKERS = args.seed, args.num_workers
    fl.set_seed(args.seed)
    print(f'Device: {torch.cuda.get_device_name(0)}',flush=True)
    print(f'FedProx mu={args.mu}, rounds={args.rounds}, local_epochs={args.local_epochs}, seed={args.seed}')
    training_pairs = fl.load_split_pairs(str(args.dataset_root/'train'))
    validation_pairs = fl.load_split_pairs(str(args.dataset_root/'val'))
    clients = fl.partition_realistic_hospitals(
        training_pairs,args.seed,fl.CLIENT_PROFILES,int(0.5*len(training_pairs)/fl.NUM_CLIENTS),
        fl.PREVALENCE_NOISE_STD,fl.PREVALENCE_CLIP,
    )
    names = [profile['name'] for profile in fl.CLIENT_PROFILES]
    config = {
        'architecture':'resnet18','algorithm':'FedProx','mu':args.mu,'seed':args.seed,
        'rounds':args.rounds,'local_epochs':args.local_epochs,'num_workers':args.num_workers,
        'batch_size':fl.BATCH_SIZE,'learning_rate':fl.LEARNING_RATE,
        'client_fraction':fl.CLIENT_FRACTION,'convergence_target':fl.CONVERGENCE_TARGET,
        'dataset_root':str(args.dataset_root.resolve()),'client_profiles':fl.CLIENT_PROFILES,
        'prevalence_noise_std':fl.PREVALENCE_NOISE_STD,'prevalence_clip':fl.PREVALENCE_CLIP,
        'class_mapping':fl.CLASS_FOLDERS,'aggregation':'sample-count-weighted model average',
        'optimizer':'Adam','loss':'weighted cross entropy plus FedProx proximal penalty',
        'selection_rule':'highest validation balanced accuracy; first round wins ties',
        'preprocessing':{'image_size':[224,224],'mean':fl.IMAGENET_MEAN,'std':fl.IMAGENET_STD},
        'test_evaluation_requested':args.evaluate_test,
    }
    (output/'run_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    with (output/'client_partition.csv').open('w',newline='',encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['simulated_client','normal','pneumonia','total'])
        for name,pairs in zip(names,clients):
            pneumonia = sum(label for _,label in pairs)
            writer.writerow([name,len(pairs)-pneumonia,pneumonia,len(pairs)])
    datasets = [fl.PneumoniaDataset(pairs,fl.train_transform) for pairs in clients]
    weights = [fl.class_weights_for(pairs,device) for pairs in clients]
    validation_loader = DataLoader(fl.PneumoniaDataset(validation_pairs,fl.eval_transform),
                                   batch_size=fl.BATCH_SIZE,shuffle=False,num_workers=args.num_workers)
    initial = fl.build_model(pretrained=True)
    initial_state = {key:value.cpu().clone() for key,value in initial.state_dict().items()}
    del initial
    client_model, evaluation_model = fl.build_model(False).to(device), fl.build_model(False).to(device)

    def save_round(history, state, best_state, best_round, best_score):
        current_round = history[-1]['round']
        with (output/'history.csv').open('w',newline='',encoding='utf-8') as file:
            writer = csv.DictWriter(file,fieldnames=list(history[0]))
            writer.writeheader()
            writer.writerows(history)
        for filename, parameters, selected_round in [('latest_model.pt',state,current_round),
                                                     ('best_model.pt',best_state,best_round)]:
            if filename == 'best_model.pt' and best_round != current_round:
                continue
            temporary = output/(filename+'.tmp')
            torch.save({'model_state_dict':parameters,'config':config,'round':selected_round,
                        'best_validation_balanced_accuracy':best_score},temporary)
            temporary.replace(output/filename)
        (output/'selection.json').write_text(json.dumps({'best_round':best_round,
            'best_validation_balanced_accuracy':best_score,'completed_round':current_round},indent=2))
        save_status(output, state='running', completed_round=current_round,
                    best_round=best_round, best_validation_balanced_accuracy=best_score)

    run = fl.run_federated('FedProx',args.mu,initial_state,datasets,weights,names,
                           validation_loader,device,client_model,evaluation_model,on_round_end=save_round)
    evaluation_model.load_state_dict(run['best_state'])
    _, labels, predictions, probabilities = fl.evaluate(evaluation_model,validation_loader,device)
    metrics = fl.compute_metrics(labels,predictions,probabilities)
    (output/'validation_metrics.json').write_text(json.dumps(metrics,indent=2))
    print(f"Best checkpoint: round {run['best_round']}; validation balanced accuracy={run['best_val_balanced_accuracy']:.4f}")
    if args.evaluate_test:
        test_pairs = fl.load_split_pairs(str(args.dataset_root/'test'))
        loader = DataLoader(fl.PneumoniaDataset(test_pairs,fl.eval_transform),batch_size=fl.BATCH_SIZE,
                            shuffle=False,num_workers=args.num_workers)
        _, labels, predictions, probabilities = fl.evaluate(evaluation_model,loader,device)
        test_metrics = fl.compute_metrics(labels,predictions,probabilities)
        (output/'test_metrics.json').write_text(json.dumps(test_metrics,indent=2))
        print('Test metrics for the validation-selected checkpoint:',test_metrics)
    print(f'Outputs saved in {output}',flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root',type=Path,default=Path(r'D:\dataset_patientsplit'))
    parser.add_argument('--rounds',type=int,default=20)
    parser.add_argument('--local-epochs',type=int,default=3)
    parser.add_argument('--mu',type=float,default=0.01,help='Provisional prototype choice; no grid search.')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--num-workers',type=int,default=0)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--evaluate-test',action='store_true',help='Evaluate the final validation-selected checkpoint once on test.')
    args = parser.parse_args()
    if args.rounds < 1 or args.local_epochs < 1 or args.mu <= 0 or args.num_workers < 0:
        parser.error('rounds, local-epochs and mu must be positive; num-workers must be nonnegative.')
    for name in ('train','val'):
        if not (args.dataset_root/name).is_dir():
            parser.error(f'Missing dataset split: {args.dataset_root/name}')
    output = args.output_dir or ROOT/'fedprox_outputs'/datetime.now(timezone.utc).strftime('run_%Y%m%dT%H%M%S_%fZ')
    if output.exists() and any(output.iterdir()):
        parser.error(f'Refusing to overwrite a nonempty output directory: {output}')
    output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TORCH_HOME',str(ROOT/'_torch_cache'))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'_mpl_cache'))
    started = stamp()
    save_status(output, state='running', started_utc=started, pid=os.getpid(),
                total_rounds=args.rounds, completed_round=0, test_evaluation_requested=args.evaluate_test)
    record(f'Single FedProx command start: {sys.executable} {sys.argv}; output={output}; start={started}')
    try:
        with (output/'console.log').open('w',encoding='utf-8') as file:
            with contextlib.redirect_stdout(Tee(sys.stdout,file)), contextlib.redirect_stderr(Tee(sys.stderr,file)):
                train(args,output)
    except BaseException as exc:
        save_status(output, state='failed', ended_utc=stamp(), error=f'{type(exc).__name__}: {exc}')
        record(f'Single FedProx command ended with {type(exc).__name__}: {exc}; completed-round checkpoints preserved in {output}')
        raise
    else:
        save_status(output, state='completed', ended_utc=stamp())
        record(f'Single FedProx command succeeded; end={stamp()}; outputs={output}')


if __name__ == '__main__':
    with training_guard():
        main()
