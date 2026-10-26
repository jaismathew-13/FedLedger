"""Local-only IPFS transport and durable architecture artifacts."""
import hashlib
import json
from pathlib import Path
import re
import time
import tempfile

import requests
from progress_display import ProgressBar

ROOT = Path(__file__).resolve().parent
IPFS_REPO = ROOT / '.ipfs-local'


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return '0x' + value.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Short independent names avoid Windows MAX_PATH failures in nested attempts.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.json-', suffix='.tmp', delete=False) as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        temporary = Path(stream.name)
    try:
        # Windows readers/virus scanners can briefly prevent atomic replacement.
        for attempt in range(40):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.025)
    finally:
        temporary.unlink(missing_ok=True)


_NO_DEFAULT = object()

def read_json(path, default=_NO_DEFAULT):
    """Retry transient Windows sharing conflicts with atomic writers."""
    path=Path(path)
    for attempt in range(40):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            if attempt==39: raise
            time.sleep(.025)
        except FileNotFoundError:
            if default is not _NO_DEFAULT: return default
            if attempt==39: raise
            time.sleep(.025)


class LocalIPFS:
    """Admin RPC is fixed to the project's isolated loopback node."""
    endpoint = 'http://127.0.0.1:5002/api/v0/'

    def __init__(self, progress_position=1):
        self.progress_position = progress_position
        self.session = requests.Session()
        self.session.trust_env = False
        marker = IPFS_REPO / 'offline-only.json'
        if not marker.is_file():
            raise RuntimeError('Initialize the isolated IPFS repo using ipfs/setup_ipfs.py first.')
        configured = json.loads((IPFS_REPO / 'config').read_text(encoding='utf-8'))
        if configured['Addresses']['Swarm'] or configured.get('Bootstrap'):
            raise RuntimeError('Refusing IPFS repo with swarm listeners or bootstrap peers.')
        isolation = json.loads(marker.read_text())
        if isolation.get('mode') == 'private-no-peers':
            if (not (IPFS_REPO/'swarm.key').is_file() or configured.get('Routing', {}).get('Type') != 'none'
                    or configured.get('AutoConf', {}).get('Enabled') is not False):
                raise RuntimeError('Private local node requires its swarm key and disabled routing.')
            peers = self.post('swarm/peers').json().get('Peers')
            if peers:
                raise RuntimeError('Refusing model upload while unexpected IPFS peers are connected.')
        identity = self.post('id').json()
        if identity['ID'] != configured['Identity']['PeerID']:
            raise RuntimeError('The IPFS API belongs to a different repo.')
        network_addresses = [address for address in (identity.get('Addresses') or [])
                             if address != '/p2p/' + identity['ID']]
        if network_addresses:
            raise RuntimeError('Expected isolated IPFS with no advertised network addresses.')

    def post(self, method, **kwargs):
        response = self.session.post(self.endpoint + method, timeout=(10, 300), **kwargs)
        response.raise_for_status()
        return response

    def add(self, path):
        with Path(path).open('rb') as stream:
            response = self.post('add', params={'pin': 'true', 'cid-version': '1', 'progress': 'true'},
                                 files={'file': ('model.pt', stream, 'application/octet-stream')}, stream=True)
            cid = None
            with response, ProgressBar(total=Path(path).stat().st_size, desc='IPFS import '+Path(path).name,
                    unit='B', unit_scale=True, position=0, disable=self.progress_position == -1, leave=False, dynamic_ncols=True) as bar:
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get('Bytes') is not None:
                        bar.update(max(0, int(event['Bytes']) - bar.n))
                    if event.get('Hash'):
                        cid = event['Hash']
                if cid is None:
                    raise RuntimeError('IPFS add returned no CID.')
                bar.update(max(0, bar.total - bar.n))
        self.validate_cid(cid)
        return {'cid': cid, 'sha256': sha256(path)}

    @staticmethod
    def validate_cid(cid):
        if not isinstance(cid, str) or not re.fullmatch(r'b[a-z2-7]{20,127}', cid):
            raise ValueError('Expected a bare base32 CIDv1.')

    def fetch(self, cid, expected_sha256, target):
        self.validate_cid(cid)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.download')
        try:
            with self.post('cat', params={'arg': cid}, stream=True) as response, temporary.open('wb') as stream:
                size = 0
                total = int(response.headers['Content-Length']) if response.headers.get('Content-Length') else None
                with ProgressBar(total=total, desc='IPFS retrieve '+target.name, unit='B', unit_scale=True,
                          position=0, disable=self.progress_position == -1, leave=False, dynamic_ncols=True) as bar:
                    for chunk in response.iter_content(1024 * 1024):
                        size += len(chunk)
                        if size > 256 * 1024 * 1024:
                            raise ValueError('Checkpoint exceeds expected ResNet-18 artifact size limit.')
                        stream.write(chunk)
                        bar.update(len(chunk))
            if sha256(temporary) != expected_sha256:
                raise ValueError('IPFS content differs from the registered checkpoint digest.')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target
