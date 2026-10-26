"""Enable Desktop-compatible isolated private networking without public peers."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT/'.ipfs-local'


def main():
    config_path = REPO/'config'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config['Addresses']['Swarm'] or config.get('Bootstrap'):
        raise RuntimeError('Expected the already-isolated project repo; refusing to modify a different setup.')
    backup = REPO/('config.before-private-mode-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    shutil.copyfile(config_path, backup)
    key = REPO/'swarm.key'
    if not key.exists():
        with key.open('x', encoding='ascii') as stream:
            stream.write('/key/swarm/psk/1.0.0/\n/base16/\n' + secrets.token_hex(32) + '\n')
    config.setdefault('Routing', {})['Type'] = 'none'
    config.setdefault('AutoConf', {})['Enabled'] = False
    config.setdefault('AutoTLS', {})['Enabled'] = False
    config.setdefault('DNS', {})['Resolvers'] = {}
    config['Routing']['DelegatedRouters'] = []
    config.setdefault('Ipns', {})['DelegatedPublishers'] = []
    config.setdefault('Discovery', {}).setdefault('MDNS', {})['Enabled'] = False
    config['Addresses']['Swarm'] = []
    config['Bootstrap'] = []
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    (REPO/'offline-only.json').write_text(json.dumps({'offline_only': False,
        'mode': 'private-no-peers', 'no_public_network': True,
        'reason': 'Desktop connectivity check needs online-mode stats/bw; private swarm, no listeners, no bootstrap, no routing instead.'}, indent=2))
    with (ROOT/'RUN_LOG.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{datetime.now(timezone.utc).isoformat()} Prepared Desktop-compatible isolated private mode: generated local swarm key (not displayed), no swarm listeners/bootstrap/mDNS/routing. Strict --offline removed only on restart. Repo config backup={backup}. No uploads.\n')
    print('Private project mode prepared. Swarm key stays local; restart Desktop to apply.')


if __name__ == '__main__':
    main()
