"""Connect installed IPFS Desktop to the project's isolated IPFS storage.

Requires local desktop-settings/process access. Does not upload any files.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path(r'C:\Program Files\IPFS Desktop\IPFS Desktop.exe')
SETTINGS = Path(os.environ['APPDATA'])/'IPFS Desktop'/'config.json'
REPO = ROOT/'.ipfs-local'


def log(message):
    with (ROOT/'RUN_LOG.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{datetime.now(timezone.utc).isoformat()} {message}\n')
    print(message, flush=True)


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def shutdown_node(session, port, expected_peer):
    if not port_open(port):
        return
    base = f'http://127.0.0.1:{port}/api/v0/'
    try:
        identity = session.post(base+'id', timeout=10)
    except requests.exceptions.ConnectionError:
        # Closing Desktop may already be taking down its child daemon.
        time.sleep(1)
        if not port_open(port):
            log(f'IPFS node on {port} already stopped with Desktop.')
            return
        raise
    identity.raise_for_status()
    if identity.json().get('ID') != expected_peer:
        raise RuntimeError(f'Refusing to stop unrelated IPFS node on {port}.')
    try:
        response = session.post(base+'shutdown', timeout=15)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        # Kubo can close the HTTP connection as it shuts down.
        pass
    for _ in range(30):
        if not port_open(port):
            log(f'Gracefully stopped verified IPFS node on port {port}.')
            return
        time.sleep(0.5)
    raise RuntimeError(f'Node on {port} still running; not launching a conflicting Desktop node.')


def main():
    log('IPFS Desktop connection start: backup saved settings, switch only Desktop repo/binary/flags; no uploads.')
    if not DESKTOP.is_file() or not SETTINGS.is_file() or not (REPO/'offline-only.json').is_file():
        raise FileNotFoundError('Installed IPFS Desktop settings or initialized project repository not found.')
    session = requests.Session()
    session.trust_env = False
    settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
    old_repo = Path(settings['ipfsConfig']['path'])
    old_config = json.loads((old_repo/'config').read_text(encoding='utf-8')) if (old_repo/'config').is_file() else None
    config = json.loads((REPO/'config').read_text(encoding='utf-8'))
    isolation = json.loads((REPO/'offline-only.json').read_text())
    private_mode = isolation.get('mode') == 'private-no-peers'
    if config['Addresses']['Swarm'] or config.get('Bootstrap'):
        raise RuntimeError('Project repository is not configured for offline isolation.')
    backup = ROOT/'archive'/'ipfs_desktop_transition'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    backup.mkdir(parents=True)
    shutil.copyfile(SETTINGS, backup/'desktop-config.before.json')
    # Close only processes running the exact installed IPFS Desktop executable.
    # This is process lifecycle management, not Windows UI automation.
    command = r'''$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -Filter "Name='IPFS Desktop.exe'" | Where-Object { $_.ExecutablePath -eq 'C:\Program Files\IPFS Desktop\IPFS Desktop.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }'''
    # Use a fixed literal command: no user text or file-derived values are interpolated.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Could not stop installed IPFS Desktop: ' + result.stderr)
    log('Stopped only the installed IPFS Desktop processes to apply saved settings.')
    old_api = old_config['Addresses']['API'] if old_config else None
    if old_api is not None and old_api != '/ip4/127.0.0.1/tcp/5001':
        if old_repo.resolve() != REPO.resolve():
            raise RuntimeError('Unexpected previous Desktop API address; refusing an assumed shutdown.')
    elif old_api == '/ip4/127.0.0.1/tcp/5001':
        shutdown_node(session, 5001, old_config['Identity']['PeerID'])
    if not private_mode:
        shutdown_node(session, 5002, config['Identity']['PeerID'])
    # Re-read after stopping the app, so cached settings cannot overwrite this change.
    settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
    # Desktop refuses to own a private-swarm repo. Its supported remote-API
    # controller can instead browse the separately managed private project node.
    desktop_repo = ROOT/'.ipfs-desktop-control' if private_mode else REPO
    if private_mode:
        desktop_repo.mkdir(exist_ok=True)
        (desktop_repo/'api').write_text('/ip4/127.0.0.1/tcp/5002', encoding='ascii')
    settings['ipfsConfig']['path'] = str(desktop_repo)
    flags = settings['ipfsConfig'].get('flags', [])
    if private_mode:
        if not (REPO/'swarm.key').is_file() or config.get('Routing', {}).get('Type') != 'none':
            raise RuntimeError('Private Desktop mode requires a swarm key and disabled routing.')
        flags = [flag for flag in flags if flag != '--offline']
    elif '--offline' not in flags:
        flags.append('--offline')
    settings['ipfsConfig']['flags'] = flags
    settings['binaryPath'] = str(ROOT/'.tools/kubo/ipfs.exe')
    temporary = SETTINGS.with_name('config.json.project-tmp')
    temporary.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    temporary.replace(SETTINGS)
    env = dict(os.environ, IPFS_PATH=str(desktop_repo))
    env.pop('IPFS_GO_EXEC', None)
    # Codex can inherit this Electron development flag; Desktop must start as GUI.
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.pop('NODE_OPTIONS', None)
    env.pop('LIBP2P_FORCE_PNET', None)  # Set on the separately managed Kubo only.
    process = subprocess.Popen([str(DESKTOP)], env=env, cwd=DESKTOP.parent,
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    log(f'Restarted IPFS Desktop PID={process.pid}; repo={REPO}; strict_offline={not private_mode}; private_no_peers={private_mode}; API5002; backup={backup}. Previous repository retained at {old_repo}.')
    for _ in range(50):
        if port_open(5002):
            identity = session.post('http://127.0.0.1:5002/api/v0/id', timeout=5)
            identity.raise_for_status()
            info = identity.json()
            network_addresses = [address for address in (info.get('Addresses') or [])
                                 if address != '/p2p/' + info['ID']]
            if info.get('ID') != config['Identity']['PeerID'] or network_addresses:
                raise RuntimeError('Desktop node identity/offline state differs from project expectations.')
            if private_mode:
                peers = session.post('http://127.0.0.1:5002/api/v0/swarm/peers', timeout=5)
                peers.raise_for_status()
                if peers.json().get('Peers'):
                    raise RuntimeError('Unexpected peers on isolated Desktop node.')
                bandwidth = session.post('http://127.0.0.1:5002/api/v0/stats/bw', headers={'Origin': 'webui://localhost'}, timeout=5)
                bandwidth.raise_for_status()
            actual = json.loads(SETTINGS.read_text(encoding='utf-8'))
            report = {'connected': True, 'desktop_repo': actual['ipfsConfig']['path'],
                      'storage_repo': str(REPO), 'daemon_managed_by': 'project_service' if private_mode else 'IPFS Desktop',
                      'api': 'http://127.0.0.1:5002', 'peer_id': info['ID'],
                      'offline': '--offline' in actual['ipfsConfig']['flags'],
                      'isolated_private_network': private_mode,
                      'backup': str(backup), 'model_uploads': False}
            (ROOT/'ipfs/desktop-connection.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            log('IPFS Desktop API verified: correct identity, no advertised swarm addresses; no files uploaded. Private mode also verified Desktop bandwidth RPC and no peers.')
            return
        if process.poll() is not None:
            raise RuntimeError(f'IPFS Desktop exited before starting the API (exit={process.returncode}). Settings/backup retained.')
        time.sleep(0.5)
    raise RuntimeError('Desktop did not expose project API within 25 seconds; inspect Desktop logs/settings backup.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'IPFS Desktop configuration error: {type(exc).__name__}: {exc}')
        raise
