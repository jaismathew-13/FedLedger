"""Local prediction/provenance dashboard; binds only to loopback."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse, parse_qs
import dashboard_data as views
from hospital_management import Management
from portal_workflow import Workflow

from architecture_io import sha256, write_json
from predict import predict_image
from train_fedprox import record

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    management = Management()
    workflow = Workflow(management)
    reference = json.loads((run/'best_global_reference.json').read_text())
    checkpoint = run/'best_model.pt'
    expected = reference['sha256']
    if sha256(checkpoint) != expected:
        raise ValueError('Best checkpoint differs from the selected model reference.')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            print(fmt % values, flush=True)

        def reply(self, value, status=200):
            data = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def bearer(self):
            return self.headers.get('Authorization', '').removeprefix('Bearer ')

        def authorized_user(self):
            token = self.bearer()
            try:
                management.admin(token)
                return 'admin'
            except PermissionError:
                profile = management.me(token)
                if not profile['application'] or profile['application']['status'] != 'approved':
                    raise PermissionError('Approved hospital membership is required for model access.')
                from blockchain.hospital_directory import Directory
                if not Directory().membership(profile['wallet'])['authorized']:
                    raise PermissionError('Hospital wallet is not authorized on the live directory.')
                return 'hospital'

        def do_GET(self):
            if urlparse(self.path).path in ('/api/blocks', '/api/current-blocks', '/api/snapshot', '/api/chain', '/api/log'):
                try:
                    management.admin(self.bearer())
                except PermissionError as exc:
                    self.reply({'error': str(exc)}, 403)
                    return
            if self.path == '/api/model':
                try:
                    self.authorized_user()
                except Exception as exc:
                    self.reply({'error': str(exc)}, 403)
                    return
            if self.path in ('/', '/admin', '/hospital'):
                page = 'admin_dashboard.html' if self.path == '/admin' else 'hospital_dashboard.html'
                data = (ROOT/page).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path in ('/assets/portal_admin.js','/assets/portal_hospital.js',
                               '/assets/dashboard_shell.js','/assets/dashboard_shell.css','/assets/current_chain_explorer.js'):
                file = ROOT/self.path.rsplit('/',1)[1]
                data=file.read_bytes()
                self.send_response(200);self.send_header('Content-Type',
                    'text/css; charset=utf-8' if file.suffix == '.css' else 'text/javascript; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
                self.end_headers();self.wfile.write(data)
            elif urlparse(self.path).path.startswith('/api/workflow/'):
                try:
                    parsed=urlparse(self.path); query=parse_qs(parsed.query); token=self.bearer()
                    if parsed.path=='/api/workflow/admin': self.reply(workflow.overview(token,admin=True))
                    elif parsed.path=='/api/workflow/me': self.reply(workflow.overview(token))
                    elif parsed.path=='/api/workflow/connectivity': self.reply(workflow.connectivity(token))
                    elif parsed.path=='/api/workflow/export': self.reply(workflow.export(token))
                    elif parsed.path=='/api/workflow/log': self.reply(workflow.local_log(token,query['campaign'][0],int(query['round'][0])))
                    else: self.reply({'error':'Not found'},404)
                except PermissionError as exc: self.reply({'error':str(exc)},403)
                except Exception as exc: self.reply({'error':str(exc)},400)
            elif self.path in ('/api/hospitals', '/api/hospitals/admin', '/api/hospitals/me'):
                try:
                    token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                    if self.path.endswith('/me'):
                        self.reply(management.me(token))
                    elif self.path.endswith('/admin'):
                        management.admin(token)
                        self.reply(management.list(token))
                    else:
                        self.reply(management.me(token))
                except PermissionError as exc:
                    self.reply({'error': str(exc)}, 403)
                except Exception as exc:
                    self.reply({'error': str(exc)}, 400)
            elif urlparse(self.path).path in ('/api/blocks', '/api/current-blocks', '/api/snapshot', '/api/chain', '/api/log'):
                try:
                    parsed = urlparse(self.path)
                    query = parse_qs(parsed.query)
                    if parsed.path == '/api/current-blocks':
                        from current_chain_explorer import current_blocks
                        self.reply(current_blocks(management,
                            end=int(query['end'][0]) if 'end' in query else None,
                            limit=int(query.get('limit',['25'])[0])))
                    elif parsed.path == '/api/blocks':
                        self.reply(views.blocks(run, live=query.get('live') == ['1']))
                    elif parsed.path == '/api/snapshot':
                        self.reply(views.snapshot(run))
                    elif parsed.path == '/api/chain':
                        self.reply(views.chain_status(run))
                    else:
                        number = int(query.get('round', ['0'])[0])
                        hospital = int(query.get('hospital', ['0'])[0])
                        if hospital not in range(3) or number not in range(1, 21):
                            raise ValueError('Invalid round/client.')
                        folder = run/'hospitals'/f'hospital_{hospital}'/f'round_{number:04d}'
                        log = folder/'training.log'
                        with log.open('rb') as stream:
                            stream.seek(max(0, log.stat().st_size - 16000))
                            text = stream.read().decode('utf-8', errors='replace')
                        self.reply({'log_tail': text, 'error': views.read(folder/'error.json'),
                                    'note': 'Quiet training logs may be empty; completion comes from artifacts.'})
                except Exception as exc:
                    self.reply({'error': str(exc)}, 400)
            elif self.path == '/api/model':
                config = json.loads((run/'run_config.json').read_text())
                self.reply({'provenance': dict(reference, contract=config['contract'],
                    chain_instance_id=config['chain_instance_id'], storage='local IPFS',
                    verification='Use live verification button; saved reference alone is not live verification'),
                    'validation': json.loads((run/'validation_metrics.json').read_text()),
                    'versions': [0]+[int(p.parent.name[6:]) for p in sorted((run/'rounds').glob('round_*/global.json'))]})
            else:
                self.reply({'error': 'Not found'}, 404)

        def do_POST(self):
            # Local-only: reject cross-origin writes; no upload persistence or public binding.
            origin = self.headers.get('Origin')
            if self.headers.get('Host') not in (f'127.0.0.1:{args.port}', f'localhost:{args.port}') or (origin and origin not in (f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}')):
                self.reply({'error': 'Local origin required'}, 403)
                return
            try:
                if urlparse(self.path).path in ('/api/audit', '/api/verify'):
                    management.admin(self.bearer())
                if urlparse(self.path).path == '/api/predict':
                    self.authorized_user()
                if self.path.startswith('/api/workflow/'):
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=16384: raise ValueError('Bounded JSON body required.')
                    payload=json.loads(self.rfile.read(size)); token=self.bearer()
                    actions={
                        '/api/workflow/prepare-agent':lambda:workflow.prepare_agent(token),
                        '/api/workflow/authorize-agent':lambda:workflow.authorize_agent(token,payload),
                        '/api/workflow/configure':lambda:workflow.configure(token,payload),
                        '/api/workflow/create':lambda:workflow.create(token,payload),
                        '/api/workflow/control':lambda:workflow.control(token,payload),
                        '/api/workflow/participate':lambda:workflow.participate(token,payload),
                        '/api/workflow/feedback':lambda:workflow.feedback(token,payload),
                    }
                    if self.path not in actions: raise ValueError('Unknown workflow action.')
                    self.reply(actions[self.path]())
                elif self.path.startswith('/api/hospitals/'):
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 16384:
                        raise ValueError('JSON request must be 1?16384 bytes.')
                    payload = json.loads(self.rfile.read(size))
                    token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                    actions = {
                        '/api/hospitals/challenge': lambda: management.challenge(payload['wallet']),
                        '/api/hospitals/login': lambda: management.login(payload['wallet'], payload['signature']),
                        '/api/hospitals/logout': lambda: management.logout(token),
                        '/api/hospitals/register': lambda: management.register(token, payload),
                        '/api/hospitals/decision': lambda: management.transition(token, payload),
                        '/api/hospitals/heartbeat': lambda: management.heartbeat(token, payload),
                        '/api/hospitals/roster': lambda: management.roster(token, payload),
                    }
                    if self.path not in actions:
                        raise ValueError('Unknown hospital action.')
                    self.reply(actions[self.path]())
                elif urlparse(self.path).path == '/api/predict':
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 20 * 1024 * 1024:
                        raise ValueError('Image upload must be between 1 byte and 20 MiB.')
                    content = self.rfile.read(size)
                    from PIL import Image
                    with Image.open(io.BytesIO(content)) as image:
                        image.verify()
                    if sha256(checkpoint) != expected:
                        raise ValueError('Checkpoint hash changed; refusing prediction.')
                    query = parse_qs(urlparse(self.path).query)
                    version = query.get('round', ['best'])[0]
                    campaign=query.get('campaign',[None])[0]
                    if campaign:
                        selected_path,selected_ref,selected=workflow.model(self.bearer(),campaign,version)
                    else:
                        selected = reference['selection_round'] if version == 'best' else int(version)
                        if selected not in range(0, 21):
                            raise ValueError('Unknown global version.')
                        selected_path = run/f'global_round_{selected:04d}.pt'
                        selected_ref = views.read(run/'initial_global.json' if selected == 0 else run/'rounds'/f'round_{selected:04d}'/'global.json')
                        if sha256(selected_path) != selected_ref['sha256']:
                            raise ValueError('Selected global checkpoint hash mismatch.')
                    prediction = predict_image(selected_path, io.BytesIO(content))
                    prediction.update(campaign=campaign, global_version=selected, cid=selected_ref['cid'],
                        checkpoint_sha256=selected_ref['sha256'], inference_utc=datetime.now(timezone.utc).isoformat(),
                        audit_reference='Local model reference only; prediction is not stored on blockchain.')
                    self.reply(prediction)
                elif urlparse(self.path).path == '/api/audit':
                    query = parse_qs(urlparse(self.path).query)
                    number = int(query.get('round', ['0'])[0])
                    hospital = int(query.get('hospital', ['0'])[0])
                    if number not in range(1, 21) or hospital not in range(3):
                        raise ValueError('Invalid round/client.')
                    self.reply(views.audit(run, number, hospital))
                elif self.path == '/api/verify':
                    result = subprocess.run([sys.executable, str(ROOT/'verify_architecture.py'),
                        '--run-dir', str(run)], capture_output=True, text=True, timeout=360, cwd=ROOT)
                    if result.returncode:
                        raise RuntimeError(result.stderr[-1500:])
                    value = json.loads(result.stdout)
                    value['verified_utc'] = datetime.now(timezone.utc).isoformat()
                    write_json(run/'live_verification.json', value)
                    self.reply(value)
                else:
                    self.reply({'error': 'Not found'}, 404)
            except PermissionError as exc:
                self.reply({'error': str(exc)}, 403)
            except Exception as exc:
                self.reply({'error': str(exc)}, 400)

    record(f'Local dashboard start: run={run}; localhost:{args.port}; images processed in memory, not saved.')
    print(f'Open http://127.0.0.1:{args.port} â€” Ctrl+C to stop.', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
