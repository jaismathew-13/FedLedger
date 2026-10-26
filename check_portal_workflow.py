"""Isolated functional checks; fixture updates are not scientific model results."""
from concurrent.futures import ThreadPoolExecutor
import base64
import csv
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from unittest.mock import patch

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image
import torch

from architecture_io import sha256, write_json, read_json
from hospital_management import Management
from portal_workflow import Workflow
import portal_workflow
from round_coordinator import run_campaign
import fedprox_core as fl

ROOT=Path(__file__).resolve().parent


class FakeDirectory:
    contract=type('Contract',(),{'address':'0x'+'1'*40})()
    client=type('Client',(),{'eth':type('Eth',(),{'chain_id':31337})()})()
    def membership(self,wallet):return {'authorized':True,'organization_hash':'0x'+'0'*64,'revision':1}
    def set(self,*args):return {'status':1,'transaction_hash':'fixture-membership','block_number':0}


class FakeDelegation:
    def authorize(self,*args):return {'status':1,'transaction_hash':'fixture-delegation','block_number':0}
    def eligible(self,*args):return True


class Value:
    def __init__(self,value):self.value=value
    def call(self):return self.value


class FixtureChain:
    """In-memory state enforces commitment/sequence/idempotency, no chain writes."""
    def __init__(self,**kwargs):
        self.hospitals=kwargs['hospital_accounts'];self.run=None;self.globals={};self.updates={};self.reviews={};self.counter=0
        self.contract=type('Contract',(),{'functions':self})()
        self.client=type('Client',(),{'eth':type('Eth',(),{'get_balance':lambda *a:10**20})(),
                                   'to_wei':lambda *a:10**18})()
        self.coordinator='fixture'
    def getRun(self,id):return Value(self.run or [False,b'\x00'*32,self.hospitals,False,0])
    def getReview(self,id,n,h,r):return Value(self.reviews.get((n,h,r),(False,False,0,b'\x00'*32)))
    def receipt(self):
        self.counter+=1
        return {'status':1,'transaction_hash':'fixture-'+str(self.counter),'block_number':self.counter,'gas_used':0}
    def open_run(self,id,policy):
        assert self.run is None
        self.run=[True,bytes.fromhex(policy[2:]),self.hospitals,True,0]
        return self.receipt()
    def publish_global(self,id,n,artifact,evidence):
        assert n not in self.globals
        self.globals[n]=dict(artifact,evidence_hash=evidence);return self.receipt()
    def global_model(self,id,n):
        if n not in self.globals:raise RuntimeError('No published global model for requested round.')
        return self.globals[n]
    def update(self,id,n,h):
        if (n,h) not in self.updates:return {'exists':False}
        row=dict(self.updates[n,h]);reviews=[v for (a,b,c),v in self.reviews.items() if (a,b)==(n,h)]
        row['accepted']=len(reviews)==2 and all(r[1] for r in reviews);return row
    def submit_update(self,id,n,h,artifact,samples,parent):
        assert (n,h) not in self.updates
        self.updates[n,h]=dict(artifact,exists=True,samples=samples,parent_sha256=parent)
        return self.receipt()
    def review(self,id,n,h,r,valid,baseline,candidate,evidence):
        assert (n,h,r) not in self.reviews
        score=lambda v:.5*(v[0]/(v[0]+v[1])+v[2]/(v[2]+v[3]))
        approved=valid and score(candidate)>.5 and score(candidate)>=score(baseline)
        self.reviews[n,h,r]=(True,approved,0,bytes.fromhex(evidence[2:]));return self.receipt()


class FakeResponse:
    def __init__(self,ok,value=None):self.ok=ok;self.value=value
    def json(self):return self.value


class FixtureTransport:
    def __init__(self,**kwargs):self.content={};self.names={};self.endpoint='fixture/';self.session=self
    def add(self,path):
        data=Path(path).read_bytes();digest=hashlib.sha256(data).digest()
        cid='b'+base64.b32encode(digest).decode().lower().rstrip('=');self.content[cid]=data
        return {'cid':cid,'sha256':'0x'+digest.hex()}
    def fetch(self,cid,digest,target):
        # Original initial model is never consumed by the fixture worker.
        data=self.content.get(cid,b'fixture-initial-global')
        if cid in self.content:assert '0x'+hashlib.sha256(data).hexdigest()==digest
        Path(target).parent.mkdir(parents=True,exist_ok=True);Path(target).write_bytes(data);return Path(target)
    def post(self,method,params=None,**kwargs):
        method=method.removeprefix(self.endpoint)
        if method=='files/stat':return FakeResponse(params['arg'] in self.names,{'Hash':self.names.get(params['arg'])})
        if method=='files/cp':
            arguments=[v for k,v in params];self.names[arguments[1]]=arguments[0].split('/')[-1]
        return FakeResponse(True,{})


def metrics(correct=True):
    import numpy as np
    return fl.compute_metrics(np.array([0,0,1,1]),np.array([0,0,1,1] if correct else [0,1,0,1]),np.array([.1,.2,.8,.9] if correct else [.1,.7,.3,.9]))


def main():
    torch.set_num_threads(2)
    state=ROOT/'local_operations'/'test_fixtures'/str(uuid.uuid4());state.mkdir(parents=True)
    management=Management(state);flow=Workflow(management);admin=management.keyfile.read_text()
    checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    def denied(name,fn):
        try:fn()
        except (ValueError,PermissionError):check(name,True)
        else:check(name,False)
    result={'kind':'isolated_software_fixture_not_model_accuracy','checks':checks,'state':str(state)}
    try:
        with patch('hospital_management.Directory',FakeDirectory),patch('portal_workflow.Directory',FakeDirectory),patch('portal_workflow.ClientAuthorization',FakeDelegation):
            tokens=[];identities=[]
            for h in range(3):
                owner=Account.create();challenge=management.challenge(owner.address)
                signature=owner.sign_message(encode_defunct(text=challenge['message'])).signature.hex()
                login=management.login(owner.address,signature);token=login['token'];tokens.append(token)
                denied('Wallet nonce cannot be replayed '+str(h),lambda:management.login(owner.address,signature))
                application=management.register(token,{'code':'FIXTURE_'+str(h),'name':'Fixture hospital '+str(h)})
                identities.append(application['id']);management.transition(admin,{'id':application['id'],'action':'approve','reason':'Isolated software fixture only'})
                agent=flow.prepare_agent(token)
                consent=owner.sign_message(encode_defunct(text=agent['message'])).signature.hex()
                flow.authorize_agent(token,{'signature':consent})
                root=flow.folder(application['id']);mapping=[]
                for i,(split,label) in enumerate((('train','NORMAL'),('train','PNEUMONIA'),('val','NORMAL'),('val','PNEUMONIA'))):
                    path=root/split/label/'sample.png';Image.new('L',(32,32),h*40+i).save(path)
                    mapping.append([path.relative_to(root).as_posix(),'fixture-patient-'+str(i)])
                with (root/'patients.csv').open('w',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(['relative_path','patient_id']);writer.writerows(mapping)
                summary=flow.configure(token,{'patient_namespace':'fixture_'+str(h)})
                check('Own local data configuration '+str(h),summary['summary']['train_images']==2)
            denied('Hospital cannot create campaign',lambda:flow.create(tokens[0],{}))
            denied('Invalid approved configuration refused',lambda:flow.create(admin,{'hospital_ids':identities,'rounds':1,'configuration':'unsupported'}))
            document=flow.create(admin,{'hospital_ids':identities,'rounds':1,'configuration':'registered_fedprox_v1'})
            identity=document['id'];folder=flow.campaign_folder(identity)
            check('Own workspace filters other hospitals',len(flow.overview(tokens[0])['campaigns'][0]['registration']['participants'])==1)
            own=json.dumps(flow.overview(tokens[0]));check('Own overview excludes other hospital identities',identities[1] not in own and identities[2] not in own)
            administrative=json.dumps(flow.overview(admin,admin=True));check('Admin metadata excludes raw data paths',str(flow.folder(identities[0])) not in administrative)
            denied('Cannot start without participant opt-in',lambda:flow.control(admin,{'campaign':identity,'command':'start'}))
            for token in tokens:flow.participate(token,{'campaign':identity,'join':True})
            flow.control(admin,{'campaign':identity,'command':'start'})
            transport=FixtureTransport();holder={};fail_once={'value':True}
            def factory(**kwargs):
                if 'chain' not in holder:holder['chain']=FixtureChain(**kwargs)
                return holder['chain']
            def train(job):
                local=Path(job['folder']);path=local/'local_model.pt'
                torch.save({'model_state_dict':{'weight':torch.tensor([float(job['hospital'])])}},path)
                item=dict(transport.add(path),hospital_id=job['hospital'],sample_count=2)
                write_json(local/'update.json',item);write_json(local/'local_validation.json',metrics());return item
            def review(job):
                if fail_once['value']:
                    fail_once['value']=False;raise RuntimeError('Injected fixture review failure')
                values=[]
                for h,item in job['updates'].items():
                    if h==job['hospital']:continue
                    evidence={'hospital_id':h,'reviewer_id':job['hospital'],'round':job['round'],
                        'sha256':item['sha256'],'cid':item['cid'],'valid':True,'baseline':metrics(False),
                        'candidate':metrics(h!=1)}
                    path=Path(job['folder'])/f'review_of_{h}.json';write_json(path,evidence)
                    values.append({'evidence':evidence,'path':str(path)})
                return values
            def evaluate(job):return {'loss':.2,'labels':[0,0,1,1],'predictions':[0,0,1,1],'scores':[.1,.2,.8,.9],'metrics':metrics()}
            functions={'train':train,'review':review,'evaluate':evaluate}
            kwargs={'functions':functions,'chain_factory':factory,'transport_factory':lambda **kw:transport,
                'state_loader':lambda path:torch.load(path,weights_only=True)['model_state_dict']}
            try:run_campaign(flow,identity,executor=ThreadPoolExecutor(max_workers=3),**kwargs)
            except RuntimeError:pass
            check('Failure checkpoint preserved',read_json((folder/'status.json'))['state']=='failed')
            check('Submitted artifacts preserved before retry',len(holder['chain'].updates)==3)
            flow.control(admin,{'campaign':identity,'command':'retry'})
            errors=[]
            def continue_run():
                try:run_campaign(flow,identity,executor=ThreadPoolExecutor(max_workers=3),**kwargs)
                except Exception as exc:
                    import traceback
                    errors.append(traceback.format_exc())
            thread=threading.Thread(target=continue_run);thread.start()
            deadline=time.time()+30
            while time.time()<deadline:
                status=read_json((folder/'status.json'))
                if status.get('phase')=='aggregation_ready' and status['state']=='paused':break
                if errors:break
                time.sleep(.1)
            result['retry_errors']=errors
            check('Validated updates wait for aggregation approval',status.get('phase')=='aggregation_ready' and not errors)
            flow.control(admin,{'campaign':identity,'command':'aggregate'})
            thread.join(30);check('Retry completes without duplicate submissions',not thread.is_alive() and not errors and len(holder['chain'].updates)==3)
            public=json.loads((folder/'round_0001/public.json').read_text())
            check('Accepted/rejected decisions use documented rule',[c['decision']['accepted'] for c in public['clients']]==[True,False,True])
            check('Validation report CIDs and global CID recorded',bool(public['global']['cid']) and all(len(c['reviews'])==2 for c in public['clients']))
            check('Completed campaign cannot restart',read_json((folder/'status.json'))['state']=='completed')
            denied('Completed campaign control refuses restart',lambda:flow.control(admin,{'campaign':identity,'command':'start'}))
            flow.feedback(admin,{'campaign':identity,'hospital':identities[0],'message':'Fixture own feedback'})
            check('Feedback only reaches recipient',len(flow.overview(tokens[0])['campaigns'][0]['feedback'])==1 and not flow.overview(tokens[1])['campaigns'][0]['feedback'])
            exports=json.dumps(flow.export(admin));check('Audit export excludes raw paths and keys',str(flow.folder(identities[0])) not in exports and 'client.key' not in exports)
            denied('Hospital cannot access another campaign log',lambda:flow.local_log(tokens[0],str(uuid.uuid4()),1))
            def case_campaign():
                case=flow.create(admin,{'hospital_ids':identities,'rounds':1,'configuration':'registered_fedprox_v1'})
                for token in tokens:flow.participate(token,{'campaign':case['id'],'join':True})
                flow.control(admin,{'campaign':case['id'],'command':'start'})
                return case
            case=case_campaign();case_id=case['id'];case_folder=flow.campaign_folder(case_id)
            flow.control(admin,{'campaign':case_id,'command':'pause'})
            case_holder={};case_errors=[]
            def case_factory(**kw):
                if 'chain' not in case_holder:case_holder['chain']=FixtureChain(**kw)
                return case_holder['chain']
            def run_case():
                try:run_campaign(flow,case_id,executor=ThreadPoolExecutor(max_workers=3),functions=functions,
                    chain_factory=case_factory,transport_factory=lambda **kw:transport,
                    state_loader=kwargs['state_loader'])
                except Exception as exc:case_errors.append(type(exc).__name__)
            thread=threading.Thread(target=run_case);thread.start()
            deadline=time.time()+10
            while time.time()<deadline:
                state_path=case_folder/'status.json'
                if state_path.exists() and read_json(state_path).get('state')=='paused':break
                time.sleep(.05)
            check('Pause prevents work before safe boundary','chain' not in case_holder)
            flow.control(admin,{'campaign':case_id,'command':'resume'})
            deadline=time.time()+15
            while time.time()<deadline:
                current=read_json((case_folder/'status.json'))
                if current.get('phase')=='aggregation_ready' or case_errors:break
                time.sleep(.1)
            check('Resume reaches validated aggregation checkpoint',current.get('phase')=='aggregation_ready' and not case_errors)
            flow.control(admin,{'campaign':case_id,'command':'cancel'});thread.join(10)
            check('Cancel stops before global publication',not thread.is_alive() and read_json((case_folder/'status.json'))['state']=='cancelled' and 1 not in case_holder['chain'].globals)
            denied('Cancelled campaign cannot be resumed',lambda:flow.control(admin,{'campaign':case_id,'command':'resume'}))
            case=case_campaign();case_id=case['id'];case_folder=flow.campaign_folder(case_id)
            case['timeout_seconds']=.05
            write_json(case_folder/'registration.json',case)
            with management.connection() as db:db.execute('UPDATE campaigns SET document=? WHERE id=?',(json.dumps(case),case_id))
            case_holder={}
            def slow_train(job):time.sleep(.2);return train(job)
            slow=dict(functions,train=slow_train)
            try:run_campaign(flow,case_id,executor=ThreadPoolExecutor(max_workers=3),functions=slow,
                chain_factory=case_factory,transport_factory=lambda **kw:transport,state_loader=kwargs['state_loader'])
            except RuntimeError:pass
            check('Timed-out local work cannot submit updates',not case_holder['chain'].updates and read_json((case_folder/'status.json'))['state']=='failed')
            management.logout(tokens[0]);denied('Sign-out revokes wallet session',lambda:management.me(tokens[0]))
            result['completed']=True
    finally:
        attempts=ROOT/'multiseed_outputs/portal_workflow_test_attempts';attempts.mkdir(exist_ok=True)
        write_json(attempts/(state.name+'.json'),result)
        target=ROOT/'multiseed_outputs/portal_workflow_checks.json';write_json(target,result)
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
