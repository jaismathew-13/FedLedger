"""Start project-local Hardhat/IPFS services without changing PowerShell policy."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from architecture_io import write_json
from train_fedprox import record

ROOT = Path(__file__).resolve().parent


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def start(name):
    env = dict(os.environ)
    if name == 'hardhat':
        folder = ROOT/'blockchain'
        runtime = json.loads((ROOT/'.tools/node-runtime.json').read_text())['folder']
        command = [str(ROOT/'.tools'/runtime/'node.exe'), str(folder/'node_modules/hardhat/dist/src/cli.js'),
                   'node', '--hostname', '127.0.0.1', '--port', '8545']
        port, prefix = 8545, 'chain'
    else:
        folder = ROOT/'ipfs'
        if not (ROOT/'.ipfs-local/offline-only.json').is_file():
            raise RuntimeError('Initialize isolated IPFS repo first.')
        env['IPFS_PATH'] = str(ROOT/'.ipfs-local')
        mode = json.loads((ROOT/'.ipfs-local/offline-only.json').read_text())
        private_mode = mode.get('mode') == 'private-no-peers'
        command = [str(ROOT/'.tools/kubo/ipfs.exe'), 'daemon']
        if private_mode:
            if not (ROOT/'.ipfs-local/swarm.key').is_file():
                raise RuntimeError('Private IPFS mode requires its local swarm key.')
            env['LIBP2P_FORCE_PNET'] = '1'
        else:
            command.append('--offline')
        port, prefix = 5002, 'daemon'
    if listening(port):
        print(f'Port {port} already has a listener; no duplicate service started. Use preflight for identity checks.')
        return
    for suffix in ('stdout', 'stderr'):
        old = folder/f'{prefix}.{suffix}.log'
        if old.exists():
            history = folder/'service-log-history'
            history.mkdir(exist_ok=True)
            old.rename(history/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '_' + old.name))
    record('Service command start: ' + subprocess.list2cmdline(command))
    with (folder/f'{prefix}.stdout.log').open('wb') as out, (folder/f'{prefix}.stderr.log').open('wb') as err:
        process = subprocess.Popen(command, cwd=folder, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    write_json(folder/f'{prefix}-process.json', {'pid': process.pid,
               'startedUtc': datetime.now(timezone.utc).isoformat(),
               'offlineOnly': '--offline' in command, 'privateNetwork': env.get('LIBP2P_FORCE_PNET') == '1'})
    for _ in range(20):
        if process.poll() is not None:
            raise RuntimeError(f'{name} exited; inspect {folder}/{prefix}.stderr.log')
        if listening(port):
            print(f'{name} listening on localhost:{port}; PID {process.pid}')
            record(f'{name} service started PID={process.pid} on loopback:{port}.')
            return
        time.sleep(0.5)
    raise RuntimeError(f'{name} did not become ready in 10 seconds; inspect logs before retrying.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=('hardhat', 'ipfs'))
    args = parser.parse_args()
    try:
        start(args.service)
    except Exception as exc:
        record(f'Service start error: {type(exc).__name__}: {exc}')
        raise
