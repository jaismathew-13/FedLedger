"""Explicit integration checks requested by the user; no training or chain writes."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image

import dashboard_data

ROOT = Path(__file__).resolve().parent
RUN = ROOT/'architecture_outputs/run_20261020T093433_860908Z'


def main():
    session = requests.Session(); session.trust_env = False
    from hospital_management import STATE
    session.headers['Authorization'] = 'Bearer '+(STATE/'admin.key').read_text(encoding='utf-8').strip()
    base = 'http://127.0.0.1:8765'
    report = {'checks': [], 'visual_browser_check': 'blocked: computer/browser inventory empty',
              'prediction_input': 'synthetic gray image; software wiring only, no clinical interpretation'}
    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)
    try:
        response = session.get(base+'/admin', timeout=20)
        check('HTML serves all six sections', response.ok and all(f'id="{name}"' in response.text
              for name in ('overview', 'monitor', 'performance', 'explorer', 'audit', 'prediction')))
        check('Responsive CSS present (not visual verification)', '@media(max-width:850px)' in response.text)
        snapshot = session.get(base+'/api/snapshot', timeout=30).json()
        check('Round history and saved global versions available', len(snapshot['history']) == 20 and len(snapshot['rounds']) == 20)
        blocks = session.get(base+'/api/blocks?live=1', timeout=120).json()['blocks']
        check('Saved receipts verified against current chain', bool(blocks) and all(b['live_receipt_verified'] for b in blocks))
        for number, hospital, accepted in ((1, 0, True), (2, 0, False), (11, 1, False)):
            response = session.post(base+f'/api/audit?round={number}&hospital={hospital}', timeout=180)
            response.raise_for_status(); audit = response.json()
            check(f'Round {number} client {hospital}: acceptance matches', audit['accepted_on_chain'] == accepted)
            check(f'Round {number} client {hospital}: integrity checks',
                  all(v['verified'] for v in audit['models']) and all(v['verified'] for v in audit['validation_reports'])
                  and audit['aggregation_evidence']['verified'])
        image = io.BytesIO(); Image.new('RGB', (224, 224), (128, 128, 128)).save(image, format='PNG')
        for version in ('best', '1', '20'):
            response = session.post(base+'/api/predict?round='+version, data=image.getvalue(),
                headers={'Content-Type': 'application/octet-stream'}, timeout=120)
            response.raise_for_status(); prediction = response.json()
            expected = 11 if version == 'best' else int(version)
            check(f'Prediction version {version}: model selection and response',
                  prediction['global_version'] == expected and bool(prediction['inference_utc'])
                  and prediction['predicted_class'] in ('NORMAL', 'PNEUMONIA')
                  and abs(sum(prediction['model_scores'].values())-1) < 1e-5)
        response = session.post(base+'/api/predict', data=b'not an image', timeout=20)
        check('Invalid image returns clear error', response.status_code == 400 and bool(response.json()['error']))
        response = session.post(base+'/api/audit?round=99&hospital=0', timeout=20)
        check('Invalid round returns clear error', response.status_code == 400 and bool(response.json()['error']))
        with patch.object(dashboard_data, 'ProtocolChain', side_effect=RuntimeError('Simulated unavailable chain')):
            status = dashboard_data.chain_status(RUN)
            check('Unavailable chain status explicit (simulation)', not status['connected'] and 'Simulated' in status['error'])
        with patch.object(dashboard_data, 'LocalIPFS', side_effect=RuntimeError('Simulated unavailable IPFS')):
            try:
                dashboard_data.audit(RUN, 1, 0)
            except RuntimeError as exc:
                check('Unavailable IPFS error explicit (simulation)', 'Simulated unavailable IPFS' in str(exc))
            else:
                check('Unavailable IPFS error explicit (simulation)', False)
        report['completed'] = True
    finally:
        target = ROOT/'multiseed_outputs/project_integration_checks.json'
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
