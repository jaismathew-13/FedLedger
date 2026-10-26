/* Hospital-only client/data and participation view; all access is owner-scoped server-side. */
(() => {
 const el=id=>document.getElementById(id);let data;
 const section=document.createElement('section');section.className='card chain-section';section.id='clientWorkspace';
 section.innerHTML=`<div class="eyebrow">Your local hospital client</div><h2>Local data &amp; training workspace</h2>
 <p class="muted">No MetaMask private-key export is needed. Authorize a separate development client and configure only your hospital-owned folder. Other hospital users and admin APIs cannot view its raw files.</p>
 <div class="controls"><button id="clientPrepare">Prepare local client</button><button id="clientSign" disabled>Sign client authorization</button></div>
 <textarea id="clientMessage" rows="5" readonly style="width:100%" aria-label="Client authorization message"></textarea>
 <h3>Your data folder</h3><pre id="clientFolder" class="audit-output"></pre><p class="muted">Copy images into train/NORMAL, train/PNEUMONIA, val/NORMAL, val/PNEUMONIA. Original files must remain unchanged. If IDs cannot be inferred, add patients.csv with relative_path,patient_id. Use the same patient namespace for IDs from the same source. A different namespace does not prove independence.</p>
 <label>Patient-ID namespace <input id="clientNamespace" placeholder="Documented source namespace"></label><button id="clientConfigure">Check &amp; register local data</button>
 <p id="clientFolderStatus" class="muted"></p><div id="clientSummary" class="table-wrap"></div><pre id="clientNotice" class="audit-output" aria-live="polite"></pre>
 <h3>My campaigns</h3><select id="clientCampaign"></select><div class="controls"><button id="clientJoin">Start local participation</button><button id="clientStop">Stop local participation</button></div>
 <p class="muted">Participation enables your local worker when the administrator launches the coordinator. Stop is cooperative; it does not erase committed submissions. Only the approved FedProx configuration is allowed.</p>
 <div id="clientStatus" class="table-wrap"></div><div id="clientRounds" class="table-wrap"></div>
 <details><summary>My validation reports, decisions, CIDs and feedback</summary><pre id="clientDetails" class="audit-output"></pre></details>
 <label>Round <input id="clientLogRound" type="number" min="1" value="1"></label><button id="clientLog">Load my local log</button><pre id="clientLogText" class="audit-output"></pre>`;
 el('participation').parentElement.after(section);section.hidden=true;
 function tableHere(id,headers,rows){let t=document.createElement('table');let tr=document.createElement('tr');for(let label of headers){let th=document.createElement('th');th.textContent=label;tr.append(th)}t.append(tr);for(let row of rows){tr=document.createElement('tr');for(let v of row){let td=document.createElement('td');td.textContent=v??'Not recorded';tr.append(td)}t.append(tr)}el(id).replaceChildren(t)}
 async function api(path,payload){return request('/api/workflow/'+path,payload)}
 async function act(fn){try{let d=await fn();if(d!==undefined)el('clientNotice').textContent=JSON.stringify(d,null,2)}catch(e){el('clientNotice').textContent=e.message}}
 function render(){let campaign=data?.campaigns.find(c=>c.registration.id===el('clientCampaign').value);for(let id of ['clientJoin','clientStop','clientLog'])el(id).disabled=!campaign;if(!campaign){el('clientStatus').textContent='No future campaign has enrolled this hospital.';for(let id of ['clientRounds','clientDetails','clientLogText'])el(id).replaceChildren();return}let me=campaign.registration.participants[0];let state=campaign.status;tableHere('clientStatus',['Campaign','State','Round / phase','My participation'],[[campaign.registration.id,state.state,(state.round||0)+' / '+(state.phase||'not started'),campaign.participation[0]?.joined?'Opted in':'Stopped / not opted in']]);
  tableHere('clientRounds',['Round','Local training','Loss / progress','Local validation accuracy','CID','Transaction','Decision / reason','Global validation accuracy'],campaign.rounds.flatMap(r=>r.clients.map(c=>[r.round,c.state,c.progress?JSON.stringify(c.progress):'Not recorded',c.local_validation?.accuracy,c.update?.cid,c.submission_receipt?.transaction_hash,c.decision?(c.decision.accepted?'Accepted':'Rejected')+' / '+c.decision.reason:'Pending',c.global_validation?.accuracy])));
  el('clientDetails').textContent=JSON.stringify({approved_parameters:campaign.registration.configuration,rounds:campaign.rounds,feedback:campaign.feedback},null,2);
 }
 async function refresh(){if(!session||profile?.application?.status!=='approved'){section.hidden=true;data=null;return}const activeSession=session;const next=await api('me');if(session!==activeSession||profile?.application?.status!=='approved'){section.hidden=true;return}data=next;section.hidden=false;el('clientFolder').textContent=data.data_folder+'\nLast successful global synchronization: '+(data.clients[0]?.last_successful_sync||'Not yet recorded');let d=data.clients[0]?.data;el('clientFolderStatus').textContent=d&&data.clients[0]?.workspace_data_current===false?'Your registered data still uses the preserved previous folder. Click Check & register local data to register this code-named workspace for future campaigns. Existing campaign records remain unchanged.':'';tableHere('clientSummary',['Data version','Train images','Validation images','Class distribution'],[[d?.version,d?.train_images,d?.val_images,d?JSON.stringify(d.class_counts):'Not configured']]);let current=el('clientCampaign').value;el('clientCampaign').replaceChildren();for(let c of data.campaigns){let o=document.createElement('option');o.value=c.registration.id;o.textContent=c.registration.id.slice(0,8)+' / '+c.status.state;el('clientCampaign').append(o)}if(data.campaigns.some(c=>c.registration.id===current))el('clientCampaign').value=current;let versions=el('version');let currentModel=versions.value;versions.querySelectorAll('option[data-campaign]').forEach(o=>o.remove());for(let c of data.campaigns)for(let r of c.rounds.filter(r=>r.global)){let o=document.createElement('option');o.dataset.campaign=c.registration.id;o.value='portal:'+c.registration.id+':'+r.round;o.textContent='Campaign '+c.registration.id.slice(0,8)+' / global '+r.round;versions.append(o)}if([...versions.options].some(o=>o.value===currentModel))versions.value=currentModel;
  syncPredictionChoices();render();return {status:'Own client workspace refreshed'}}
 let authorizationBusy=false;
 function authorizationControls(){el('clientPrepare').disabled=authorizationBusy;el('clientSign').disabled=authorizationBusy||!el('clientMessage').value}
 el('clientPrepare').onclick=()=>act(async()=>{
  if(authorizationBusy)return;authorizationBusy=true;authorizationControls();const activeSession=session;
  try{const d=await api('prepare-agent',{});if(session!==activeSession)throw Error('Wallet session changed. Prepare the client again.');el('clientMessage').value=d.message;el('clientFolder').textContent=d.data_folder;return {delegate:d.delegate,message:'Review the message, then click Sign client authorization. Approval in MetaMask completes authorization automatically.'}}
  finally{authorizationBusy=false;authorizationControls()}
 });
 el('clientSign').onclick=()=>act(async()=>{
  if(authorizationBusy)return;
  if(!window.ethereum||!el('clientMessage').value)throw Error('Prepare a client and connect the owner wallet first.');
  const owner=profile.wallet,activeSession=session,message=el('clientMessage').value;
  authorizationBusy=true;authorizationControls();
  try{
   el('clientNotice').textContent='Connecting to MetaMask. Unlock the wallet if prompted.';
   let accounts=await window.ethereum.request({method:'eth_requestAccounts'});
   if(session!==activeSession)throw Error('Wallet session changed. Sign in and prepare the client again.');
   if(accounts[0]?.toLowerCase()!==owner.toLowerCase())throw Error('Select the signed-in hospital owner account in MetaMask.');
   el('clientNotice').textContent='Approve the client authorization message in MetaMask.';
   const signature=await window.ethereum.request({method:'personal_sign',params:[message,owner]});
   accounts=await window.ethereum.request({method:'eth_accounts'});
   if(session!==activeSession||accounts[0]?.toLowerCase()!==owner.toLowerCase())throw Error('Wallet account changed. Sign in and prepare the client again.');
   el('clientNotice').textContent='Signature approved. Recording client authorization...';
   const d=await api('authorize-agent',{signature});el('clientMessage').value='';
   await refresh();return {status:'Client authorization completed',...d};
  }catch(e){if(e.code===4001)throw Error('Authorization declined in MetaMask. You can try signing again.');if(e.code===-32002)throw Error('A MetaMask request is already pending. Open the MetaMask extension and complete or reject it before trying again.');throw e}
  finally{authorizationBusy=false;authorizationControls()}
 });
 el('clientConfigure').onclick=()=>act(async()=>{let d=await api('configure',{patient_namespace:el('clientNamespace').value});await refresh();return d});el('clientCampaign').onchange=render;
 for(let [id,join] of [['clientJoin',true],['clientStop',false]])el(id).onclick=()=>act(async()=>{let d=await api('participate',{campaign:el('clientCampaign').value,join});await refresh();return d});
 el('clientLog').onclick=()=>act(async()=>{let r=await request('/api/workflow/log?campaign='+encodeURIComponent(el('clientCampaign').value)+'&round='+Number(el('clientLogRound').value));el('clientLogText').textContent=JSON.stringify(r,null,2)});
 async function updateWorkspace(){if(!session||profile?.application?.status!=='approved'){section.hidden=true;data=null;return}try{await refresh()}catch(e){section.hidden=true;document.getElementById('notice').textContent=e.message}}
 window.addEventListener('hospital-profile-updated',updateWorkspace);
 setInterval(async()=>{if(!session)return;try{await window.refreshHospitalProfile()}catch(e){section.hidden=true;el('notice').textContent=e.message}},7000);
})();
