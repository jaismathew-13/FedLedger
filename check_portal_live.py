"""Real local-chain/IPFS integration with synthetic updates, NOT model evaluation."""
from concurrent.futures import ThreadPoolExecutor
import csv
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
from web3 import Web3

from architecture_io import LocalIPFS, read_json, write_json
from blockchain.registry import connect, instance_id, receipt
from blockchain.hospital_directory import Directory
from blockchain.client_authorization import ClientAuthorization
from blockchain.protocol_chain import ProtocolChain
from hospital_management import Management
from portal_workflow import Workflow
from round_coordinator import run_campaign
from check_portal_workflow import metrics

ROOT=Path(__file__).resolve().parent


def main():
    torch.set_num_threads(2)
    state=ROOT/'local_operations/live_test_fixtures'/str(uuid.uuid4());state.mkdir(parents=True)
    management=Management(state);flow=Workflow(management);admin=management.keyfile.read_text()
    client=connect();checks=[]
    result={'kind':'live_local_services_synthetic_updates_not_clinical_or_training_results','checks':checks,'state':str(state)}
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    def deploy(name,*args):
        artifact=read_json(ROOT/'blockchain/artifacts'/(name+'.json'))
        factory=client.eth.contract(abi=artifact['abi'],bytecode=artifact['bytecode'])
        tx=factory.constructor(*args).transact({'from':client.eth.accounts[0]})
        saved=receipt(client,tx);address=client.eth.get_transaction_receipt(tx)['contractAddress']
        result.setdefault('isolated_contract_deployments',[]).append(dict(saved,contract=name,address=address))
        return client.eth.contract(address=address,abi=artifact['abi'])
    try:
        directory=deploy('HospitalDirectory');authorization=deploy('ClientAuthorization',directory.address)
        class LiveDirectory(Directory):
            def __init__(self):self.client=client;self.instance=instance_id(client);self.contract=directory
        class LiveAuthorization(ClientAuthorization):
            def __init__(self):self.client=client;self.instance=instance_id(client);self.contract=authorization
        with patch('hospital_management.Directory',LiveDirectory),patch('portal_workflow.Directory',LiveDirectory),patch('portal_workflow.ClientAuthorization',LiveAuthorization):
            identities=[];tokens=[]
            for h in range(3):
                owner=Account.create();challenge=management.challenge(owner.address)
                token=management.login(owner.address,owner.sign_message(encode_defunct(text=challenge['message'])).signature.hex())['token']
                tokens.append(token)
                hospital=management.register(token,{'code':'LIVE_FIXTURE_'+str(h),'name':'Live synthetic fixture '+str(h)});identities.append(hospital['id'])
                management.transition(admin,{'id':hospital['id'],'action':'approve','reason':'Isolated local services test; not an actual hospital'})
                prepared=flow.prepare_agent(token)
                flow.authorize_agent(token,{'signature':owner.sign_message(encode_defunct(text=prepared['message'])).signature.hex()})
                check('Live wallet delegation authorized '+str(h),LiveAuthorization().eligible(owner.address,prepared['delegate']))
                root=flow.folder(hospital['id']);rows=[]
                for i,(split,label) in enumerate((('train','NORMAL'),('train','PNEUMONIA'),('val','NORMAL'),('val','PNEUMONIA'))):
                    path=root/split/label/'fixture.png';Image.new('L',(32,32),h*40+i).save(path)
                    rows.append([path.relative_to(root).as_posix(),f'fixture_patient_{i}'])
                with (root/'patients.csv').open('w',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(['relative_path','patient_id']);writer.writerows(rows)
                flow.configure(token,{'patient_namespace':'live_fixture_'+str(h)})
            registration=flow.create(admin,{'hospital_ids':identities,'rounds':2,'configuration':'registered_fedprox_v1'})
            identity=registration['id'];folder=flow.campaign_folder(identity)
            registration['fixture_only']='Synthetic update tensors and deterministic validation fixtures; not training results.'
            write_json(folder/'registration.json',registration)
            with management.connection() as db:db.execute('UPDATE campaigns SET document=? WHERE id=?',(json.dumps(registration),identity))
            for token in tokens:flow.participate(token,{'campaign':identity,'join':True})
            flow.control(admin,{'campaign':identity,'command':'start'})
            ipfs=LocalIPFS(progress_position=-1);holder={}
            def chain_factory(**kw):
                holder['chain']=ProtocolChain(**kw);return holder['chain']
            def train(job):
                local=Path(job['folder']);path=local/'local_model.pt'
                torch.save({'model_state_dict':{'fixture_weight':torch.tensor([float(job['hospital'])])},'fixture_only':True},path)
                artifact=dict(ipfs.add(path),hospital_id=job['hospital'],sample_count=2)
                write_json(local/'update.json',artifact);write_json(local/'local_validation.json',metrics());return artifact
            def review(job):
                values=[]
                for h,artifact in job['updates'].items():
                    if h==job['hospital']:continue
                    evidence={'hospital_id':h,'reviewer_id':job['hospital'],'round':job['round'],'valid':True,
                        'cid':artifact['cid'],'sha256':artifact['sha256'],'baseline':metrics(False),'candidate':metrics(job['round']==1 and h!=1),
                        'fixture_only':True}
                    path=Path(job['folder'])/f'review_of_{h}.json';write_json(path,evidence)
                    values.append({'path':str(path),'evidence':evidence})
                return values
            def evaluate(job):return {'labels':[0,0,1,1],'predictions':[0,0,1,1],'scores':[.1,.2,.8,.9],'loss':.2,'metrics':metrics()}
            errors=[]
            def execute():
                try:run_campaign(flow,identity,executor=ThreadPoolExecutor(max_workers=3),
                    functions={'train':train,'review':review,'evaluate':evaluate},chain_factory=chain_factory,
                    state_loader=lambda p:torch.load(p,weights_only=True)['model_state_dict'])
                except Exception:
                    import traceback
                    errors.append(traceback.format_exc())
            thread=threading.Thread(target=execute);thread.start()
            for number in (1,2):
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    status=read_json(folder/'status.json',{})
                    if (status.get('phase')=='aggregation_ready' and status.get('round')==number) or errors:break
                    time.sleep(.2)
                result['errors']=errors
                check('Signed submissions and peer reports reach live aggregation gate '+str(number),status.get('phase')=='aggregation_ready' and status.get('round')==number and not errors)
                flow.control(admin,{'campaign':identity,'command':'aggregate'})
            thread.join(90)
            result['errors']=errors
            check('Live IPFS and signed-chain workflow completed',not thread.is_alive() and not errors and read_json(folder/'status.json')['state']=='completed')
            public=read_json(folder/'round_0001/public.json')
            check('Live contract accepted/rejected decisions match policy',[v['decision']['accepted'] for v in public['clients']]==[True,False,True])
            checksums=[]
            for h,item in enumerate(public['clients']):
                destination=state/f'verified_client_{h}.pt';ipfs.fetch(item['update']['cid'],item['update']['sha256'],destination)
                for report in item['reviews'].values():ipfs.fetch(report['report_cid'],report['report_sha256'],state/f'verified_report_{h}_{report["reviewer"]}.json')
                checksums.append(True)
            check('Client artifacts and report CIDs retrieved with matching hashes',all(checksums))
            global_model=public['global'];ipfs.fetch(global_model['cid'],global_model['sha256'],state/'verified_global.pt')
            check('Sample-weighted accepted-state aggregation verified',float(torch.load(state/'verified_global.pt',weights_only=True)['model_state_dict']['fixture_weight'][0])==1.0)
            retained=read_json(folder/'round_0002/public.json')
            check('All rejected retains global bytes on live chain',not retained['eligible_updates'] and retained['global']['sha256']==global_model['sha256'])
            check('Global artifact retrieved with committed digest',True)
            result['campaign']=identity;result['completed']=True
    finally:
        if 'thread' in locals() and thread.is_alive():
            with management.connection() as db:db.execute("UPDATE campaigns SET control='cancel' WHERE id=?",(identity,))
            thread.join(15)
        attempts=ROOT/'multiseed_outputs/portal_live_test_attempts';attempts.mkdir(exist_ok=True)
        write_json(attempts/(state.name+'.json'),result)
        write_json(ROOT/'multiseed_outputs/portal_live_checks.json',result)
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
