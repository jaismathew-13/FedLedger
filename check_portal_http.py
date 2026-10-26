"""Exercise real HTTP role handlers against isolated organization fixtures."""
import io
import json
from pathlib import Path
import sys
import threading
import uuid
from unittest.mock import patch

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image
import requests

from architecture_io import write_json
from hospital_management import Management
from check_portal_workflow import FakeDirectory, FakeDelegation
import project_dashboard

ROOT=Path(__file__).resolve().parent


def main():
    state=ROOT/'local_operations/http_test_fixtures'/str(uuid.uuid4())
    state.mkdir(parents=True)
    management=Management(state);admin=management.keyfile.read_text()
    actual_server=project_dashboard.ThreadingHTTPServer
    servers=[];ready=threading.Event();errors=[]
    def server_factory(address,handler):
        server=actual_server(address,handler);servers.append(server);ready.set();return server
    def serve():
        try:project_dashboard.main()
        except Exception as exc:errors.append(repr(exc));ready.set()
    checks=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    result={'kind':'isolated_http_role_fixture_not_scientific_evaluation','checks':checks,'state':str(state)}
    context=[patch.object(project_dashboard,'Management',return_value=management),
        patch.object(project_dashboard,'ThreadingHTTPServer',side_effect=server_factory),
        patch('hospital_management.Directory',FakeDirectory),patch('portal_workflow.Directory',FakeDirectory),
        patch('portal_workflow.ClientAuthorization',FakeDelegation),
        patch('blockchain.hospital_directory.Directory',FakeDirectory),
        patch.object(sys,'argv',['project_dashboard.py','--run-dir',str(ROOT/'architecture_outputs/run_20261020T093433_860908Z'),'--port','18765'])]
    import contextlib
    try:
        with contextlib.ExitStack() as stack:
            for item in context:stack.enter_context(item)
            thread=threading.Thread(target=serve);thread.start();ready.wait(10)
            check('Isolated HTTP server started',bool(servers) and not errors)
            session=requests.Session();session.trust_env=False;base='http://127.0.0.1:18765'
            def call(path,payload=None,token=None,headers=None):
                kwargs={'timeout':120,'headers':dict(headers or {})}
                if token:kwargs['headers']['Authorization']='Bearer '+token
                return session.get(base+path,**kwargs) if payload is None else session.post(base+path,json=payload,**kwargs)
            for path in ('/admin','/hospital','/assets/portal_admin.js','/assets/portal_hospital.js','/assets/dashboard_shell.js','/assets/dashboard_shell.css','/assets/current_chain_explorer.js'):
                response=call(path);check('Page/asset available '+path,response.status_code==200)
            for path in ('/api/snapshot','/api/blocks','/api/current-blocks','/api/workflow/admin','/api/workflow/export','/api/model'):
                check('Anonymous denied '+path,call(path).status_code==403)
            check('Administrator workspace authorized',call('/api/workflow/admin',token=admin).status_code==200)
            tokens=[];ids=[];owners=[]
            for i in range(2):
                owner=Account.create();owners.append(owner)
                challenge=call('/api/hospitals/challenge',{'wallet':owner.address}).json()
                signed=owner.sign_message(encode_defunct(text=challenge['message'])).signature.hex()
                login=call('/api/hospitals/login',{'wallet':owner.address,'signature':signed})
                check('Signed hospital HTTP login '+str(i),login.status_code==200)
                token=login.json()['token'];tokens.append(token)
                application=call('/api/hospitals/register',{'code':'HTTP_'+str(i),'name':'HTTP fixture hospital '+str(i)},token)
                check('HTTP application '+str(i),application.status_code==200)
                ids.append(application.json()['id'])
            check('Pending hospital denied prediction metadata',call('/api/model',token=tokens[0]).status_code==403)
            decision=call('/api/hospitals/decision',{'id':ids[0],'action':'approve','reason':'Isolated HTTP fixture only'},admin)
            check('Admin review HTTP route works',decision.status_code==200)
            me=call('/api/hospitals/me',token=tokens[0]).json()
            check('Own status and admin feedback visible',me['application']['status']=='approved' and len(me['review_feedback'])==1)
            data=call('/api/workflow/me',token=tokens[0]);check('Own workflow HTTP route works',data.status_code==200)
            check('Own profile excludes other hospital',ids[1] not in json.dumps(me) and ids[1] not in data.text)
            for path in ('/api/snapshot','/api/current-blocks','/api/log?round=1&hospital=0','/api/workflow/admin','/api/workflow/export'):
                check('Hospital denied admin route '+path,call(path,token=tokens[0]).status_code==403)
            check('Hospital denied admin mutation',call('/api/workflow/create',{},tokens[0]).status_code==403)
            check('Cross-origin mutation refused',call('/api/workflow/control',{},admin,{'Origin':'https://untrusted.example'}).status_code==403)
            prepare=call('/api/workflow/prepare-agent',{},tokens[0]);check('Local agent preparation HTTP route works',prepare.status_code==200)
            consent=owners[0].sign_message(encode_defunct(text=prepare.json()['message'])).signature.hex()
            response=call('/api/workflow/authorize-agent',{'signature':consent},tokens[0]);check('Owner-signed delegated client accepted',response.status_code==200)
            check('Delegation nonce replay refused',call('/api/workflow/authorize-agent',{'signature':consent},tokens[0]).status_code==400)
            response=call('/api/model',token=tokens[0]);check('Approved hospital can access model reference',response.status_code==200)
            image=io.BytesIO();Image.new('L',(224,224),128).save(image,format='PNG')
            response=session.post(base+'/api/predict?round=best',data=image.getvalue(),
                headers={'Authorization':'Bearer '+tokens[0],'Content-Type':'application/octet-stream'},timeout=120)
            check('Approved hospital prediction handler works',response.status_code==200 and 'model_scores' in response.json())
            call('/api/hospitals/logout',{},tokens[0]);check('Logged-out HTTP session refused',call('/api/hospitals/me',token=tokens[0]).status_code==403)
            result['completed']=True
    finally:
        for server in servers:server.shutdown();server.server_close()
        if 'thread' in locals():thread.join(5)
        attempts=ROOT/'multiseed_outputs/portal_http_test_attempts';attempts.mkdir(exist_ok=True)
        write_json(attempts/(state.name+'.json'),result)
        write_json(ROOT/'multiseed_outputs/portal_http_checks.json',result)
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
