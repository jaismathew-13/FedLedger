"""Install project-local Ethereum requirements and record every command."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'


def log(message):
    with (ROOT / 'RUN_LOG.md').open('a', encoding='utf-8') as out:
        out.write(f'\n{datetime.now(timezone.utc).isoformat()} {message}\n')
    print(message, flush=True)


def run(command, env=None):
    log('Command start: ' + subprocess.list2cmdline([str(x) for x in command]))
    result = subprocess.run(command, cwd=ROOT / 'blockchain', env=env)
    log(f'Command end: exit={result.returncode}')
    result.check_returncode()


def main():
    log('Install requirements start; dataset and scientific training settings untouched.')
    if not (ROOT / 'requirements-before-install.txt').exists():
        (ROOT / 'requirements-before-install.txt').write_text(subprocess.check_output(
            [sys.executable, '-m', 'pip', 'freeze'], text=True), encoding='utf-8')
    log('Saved pip freeze baseline to requirements-before-install.txt.')
    run([sys.executable, '-m', 'pip', 'install', 'web3>=7,<8', '--timeout', '30', '--retries', '1'])
    TOOLS.mkdir(exist_ok=True)
    base = 'https://nodejs.org/dist/latest-v22.x/'
    log('Download official Node 22 SHASUMS256.txt and Windows x64 ZIP; verify SHA256 before extraction.')
    sums = urllib.request.urlopen(base + 'SHASUMS256.txt', timeout=60).read().decode()
    match = re.search(r'^([a-f0-9]{64})\s+(node-v22\.[0-9]+\.[0-9]+-win-x64\.zip)$', sums, re.M)
    if not match:
        raise RuntimeError('Node Windows archive missing from official checksums')
    expected, name = match.groups()
    folder = TOOLS / name.removesuffix('.zip')
    archive = TOOLS / name
    if not (folder / 'npm.cmd').is_file():
        with urllib.request.urlopen(base + name, timeout=120) as response, archive.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Node archive checksum mismatch; not extracting')
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                if not (TOOLS / item.filename).resolve().is_relative_to(TOOLS.resolve()):
                    raise RuntimeError('Unsafe archive path')
            bundle.extractall(TOOLS)
        archive.unlink()
    (TOOLS / 'node-runtime.json').write_text(json.dumps({'folder': folder.name, 'archive_sha256': expected}, indent=2))
    env = dict(os.environ, PATH=str(folder) + os.pathsep + os.environ.get('PATH', ''))
    npm = folder / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'
    run([str(folder / 'node.exe'), str(npm), 'install', '--no-fund'], env)
    run([str(folder / 'node.exe'), '--version'], env)
    run([str(folder / 'node.exe'), str(npm), '--version'], env)
    (ROOT / 'requirements-lock.txt').write_text(subprocess.check_output(
        [sys.executable, '-m', 'pip', 'freeze'], text=True), encoding='utf-8')
    log('Saved requirements-lock.txt; npm package-lock.json records Ethereum tool dependencies. Installation complete. No training or deployment.')


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        log(f'Installation error: {type(exc).__name__}: {exc}')
        raise
