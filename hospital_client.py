"""Local hospital wallet/client. Private keys never leave their local key files."""
import argparse
import json
from pathlib import Path
import time

from eth_account import Account
from eth_account.messages import encode_defunct
import requests

from hospital_management import STATE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create-wallet', 'apply', 'heartbeat', 'status'])
    parser.add_argument('--code', required=True)
    parser.add_argument('--name')
    parser.add_argument('--sample-count', type=int)
    parser.add_argument('--readiness-attested', action='store_true',
        help='Explicitly attest patient split/labels checked, local data only, and client ready.')
    parser.add_argument('--watch', action='store_true', help='Repeat heartbeat every 30s; Ctrl+C to stop.')
    args = parser.parse_args()
    import re
    code = args.code.upper()
    if not re.fullmatch(r'[A-Z0-9_-]{3,32}', code):
        parser.error('Use a 3–32 character organization code.')
    folder = STATE/'clients'/code
    keyfile = folder/'wallet.key'
    if args.command == 'create-wallet':
        folder.mkdir(parents=True, exist_ok=True)
        if keyfile.exists():
            raise RuntimeError('Wallet already exists; it will not be overwritten.')
        account = Account.create()
        with keyfile.open('x', encoding='utf-8') as stream:
            stream.write(account.key.hex())
        (folder/'wallet.json').write_text(json.dumps({'code': code, 'wallet': account.address}, indent=2))
        print('Local wallet created:', account.address)
        print('Keep wallet.key private. This is a development wallet, never use it for real funds.')
        return
    account = Account.from_key(keyfile.read_text(encoding='utf-8').strip())
    session = requests.Session(); session.trust_env = False
    base = 'http://127.0.0.1:8765'
    def post(action, payload):
        response = session.post(base+'/api/hospitals/'+action, json=payload, timeout=60)
        if not response.ok:
            raise RuntimeError(response.json().get('error', response.text))
        return response.json()
    challenge = post('challenge', {'wallet': account.address})
    signed = account.sign_message(encode_defunct(text=challenge['message']))
    login = post('login', {'wallet': account.address, 'signature': signed.signature.hex()})
    session.headers['Authorization'] = 'Bearer '+login['token']
    if args.command == 'apply':
        if not args.name:
            parser.error('--name required for application.')
        print(json.dumps(post('register', {'code': code, 'name': args.name}), indent=2))
    elif args.command == 'status':
        response = session.get(base+'/api/hospitals/me', timeout=30)
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    else:
        if not args.readiness_attested or not args.sample_count:
            parser.error('Provide --sample-count and --readiness-attested only after completing checks.')
        while True:
            print(json.dumps(post('heartbeat', {'sample_count': args.sample_count,
                'patient_split_checked': True, 'labels_checked': True,
                'local_data_only': True, 'client_ready': True})), flush=True)
            if not args.watch:
                break
            time.sleep(30)


if __name__ == '__main__':
    main()
