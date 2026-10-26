"""Install pinned Kubo locally and initialize an offline-only project repo."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.43.1'
REPO = ROOT/'.ipfs-local'
TOOLS = ROOT/'.tools'
EXE = TOOLS/'kubo'/'ipfs.exe'


def log(message):
    with (ROOT/'RUN_LOG.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{datetime.now(timezone.utc).isoformat()} {message}\n')
    print(message, flush=True)


def main():
    TOOLS.mkdir(exist_ok=True)
    if not EXE.is_file():
        name = f'kubo_v{VERSION}_windows-amd64.zip'
        # Official release mirror; dist.ipfs.tech timed out on this laptop.
        base = f'https://github.com/ipfs/kubo/releases/download/v{VERSION}/'
        log(f'Download official ipfs/kubo GitHub release {VERSION} ZIP and SHA512 checksum into .tools; verify before extraction.')
        sums = urllib.request.urlopen(base + name + '.sha512', timeout=60).read().decode()
        expected = re.search(r'\b[a-fA-F0-9]{128}\b', sums)
        if not expected:
            raise ValueError('No SHA512 digest in distribution checksum file.')
        archive = TOOLS/name
        with urllib.request.urlopen(base + name, timeout=120) as response, archive.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        actual = hashlib.sha512(archive.read_bytes()).hexdigest()
        if actual != expected.group().lower():
            raise ValueError('Kubo archive checksum mismatch; extraction refused.')
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                if not (TOOLS/item.filename).resolve().is_relative_to(TOOLS.resolve()):
                    raise ValueError('Archive path outside local tools folder.')
            bundle.extractall(TOOLS)
        archive.unlink()
        (TOOLS/'kubo-install.json').write_text(json.dumps({'version': VERSION, 'sha512': actual}, indent=2))
    env = dict(os.environ, IPFS_PATH=str(REPO), IPFS_FD_MAX='1024')
    if not (REPO/'config').exists():
        log('Command: .tools/kubo/ipfs.exe init --profile=server with project IPFS_PATH.')
        subprocess.run([str(EXE), 'init', '--profile=server'], env=env, check=True)
        config_path = REPO/'config'
        config = json.loads(config_path.read_text())
        config['Addresses']['API'] = '/ip4/127.0.0.1/tcp/5002'
        config['Addresses']['Gateway'] = '/ip4/127.0.0.1/tcp/8081'
        config['Addresses']['Swarm'] = []
        config['Bootstrap'] = []
        config.setdefault('Discovery', {}).setdefault('MDNS', {})['Enabled'] = False
        config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
        (REPO/'offline-only.json').write_text(json.dumps({'offline_only': True, 'kubo_version': VERSION}))
        log('Initialized project-only repo: no swarm listeners, no bootstrap peers, mDNS off, loopback API/gateway; start with daemon --offline.')
    elif not (REPO/'offline-only.json').is_file():
        raise RuntimeError('Existing unrecognized IPFS repo; refusing to rewrite its configuration.')
    else:
        config_path = REPO/'config'
        config = json.loads(config_path.read_text())
        if config['Addresses']['Swarm'] or config.get('Bootstrap'):
            raise RuntimeError('Refusing to rewrite a repo with network peers configured.')
        config['Addresses']['API'] = '/ip4/127.0.0.1/tcp/5002'
        config['Addresses']['Gateway'] = '/ip4/127.0.0.1/tcp/8081'
        config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
        log('Owned offline project repo API configured on 5002/gateway8081; existing service on5001 untouched.')
    subprocess.run([str(EXE), 'version'], env=env, check=True)
    log('IPFS installation/configuration complete; no model or image uploads.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'IPFS setup error: {type(exc).__name__}: {exc}')
        raise
