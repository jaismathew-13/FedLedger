/* Live chain records are separate from the earlier experiment's saved receipts. */
(() => {
 const section=document.createElement('section');section.id='currentExplorer';section.className='card chain-section';
 section.innerHTML=`<div class="row"><div><div class="eyebrow">Live local blockchain</div><h2>Current blockchain explorer</h2></div><span class="pill">Admin view</span></div>
 <p class="muted">View actual current-chain blocks, including hospital approvals, client authorizations, deployments and training transactions. Old experiment receipts remain in History.</p>
 <div class="controls"><button id="chainRefresh" class="primary">Refresh latest blocks</button><button id="chainOlder">Older blocks</button><button id="chainNewer">Newer blocks</button>
 <label>Block number <input id="chainNumber" type="number" min="0" step="1" style="width:110px"></label><button id="chainGo">Go to block</button>
 <label>Show <select id="chainCategory"><option value="all">All blocks</option><option value="membership">Hospital approvals / suspensions</option><option value="authorization">Client authorizations</option><option value="training">Training records</option></select></label></div>
 <p id="currentChainStatus" class="muted" role="status">Sign in, then refresh to load the current chain.</p>
 <div id="currentChainCards" class="chain" aria-label="Current blockchain blocks"></div>
 <h3>Selected block and transactions</h3><div id="currentBlockDetails"></div><details><summary>Full block and decoded event details</summary><pre id="currentBlockJson" class="audit-output">Select a block.</pre></details>`;
 document.getElementById('roundOperations').after(section);
 const el=id=>document.getElementById(id);let page=null;let loading=false;
 function field(label,value){let d=document.createElement('div');d.className='field';let l=document.createElement('label');l.textContent=label;let v=document.createElement('div');v.className='mono';v.textContent=value??'Not available';d.append(l,v);return d}
 function controls(){el('chainOlder').disabled=loading||page?.older_end==null;el('chainNewer').disabled=loading||page?.newer_end==null;el('chainRefresh').disabled=loading;el('chainGo').disabled=loading}
 function inspect(block){
  const details=el('currentBlockDetails');details.replaceChildren(field('Block number',block.block_number),field('Timestamp (UTC)',block.timestamp),field('Block hash',block.block_hash),field('Parent hash',block.parent_hash));
  for(const tx of block.transactions){const card=document.createElement('div');card.className='card chain-section';card.append(field('Transaction hash',tx.transaction_hash),field('Receipt status',tx.status===1?'Success':'Failed'),field('From',tx.from),field('To',tx.to||tx.created_contract),field('Contract',tx.contract_name||tx.description));
   for(const event of tx.events){let title=document.createElement('h3');title.textContent=event.title;card.append(title);for(const [key,value] of Object.entries(event.arguments))card.append(field(key,typeof value==='object'?JSON.stringify(value):value))}details.append(card)}
  if(!block.transactions.length)details.append(field('Transactions','No transactions in this block.'));
  el('currentBlockJson').textContent=JSON.stringify(block,null,2);
  el('currentChainCards').querySelectorAll('.block').forEach(card=>card.classList.toggle('selected',card.dataset.block===String(block.block_number)));
  el('currentChainCards').querySelector('.block.selected')?.scrollIntoView({block:'nearest',inline:'center'});
 }
 function render(){
  const cards=el('currentChainCards');cards.replaceChildren();if(!page)return;
  const category=el('chainCategory').value;const blocks=page.blocks.filter(b=>category==='all'||b.transactions.some(tx=>tx.events.some(e=>e.category===category)));
  for(const block of blocks){let card=document.createElement('article');card.className='block';card.dataset.block=block.block_number;let number=document.createElement('div');number.className='number';number.textContent='BLOCK #'+block.block_number;let title=document.createElement('h3');title.textContent=block.transactions.flatMap(tx=>tx.events).map(e=>e.title).join(' / ')||(block.block_number===0?'Genesis block':block.transactions[0]?.description||'Empty block');let meta=document.createElement('small');meta.textContent=block.transaction_count+' transaction(s) | '+block.timestamp;let hash=document.createElement('div');hash.className='mono';hash.textContent=block.block_hash.slice(0,18)+'...';let button=document.createElement('button');button.textContent='Inspect block';button.onclick=()=>inspect(block);card.append(number,title,meta,hash,button);cards.append(card)}
  if(!blocks.length)cards.textContent='No matching events on this page. Use Older/Newer or change the filter.';
 }
 async function load(end){
  if(loading)return;loading=true;controls();el('currentChainStatus').textContent='Reading current blockchain...';
  try{let response=await fetch('/api/current-blocks?limit=25'+(end==null?'':'&end='+encodeURIComponent(end)));let data=await response.json();if(!response.ok)throw Error(data.error||'Cannot read chain');page=data;render();el('currentBlockDetails').replaceChildren();el('currentBlockJson').textContent='Select a block.';el('currentChainStatus').textContent=data.network+' | Chain ID '+data.chain_id+' | Latest block '+data.latest_block+' | Showing '+data.start_block+' to '+data.end_block+' | Instance '+data.instance_id.slice(0,14)+'...';if(end!=null){const selected=data.blocks.find(b=>b.block_number===Number(end));if(selected)inspect(selected)}}catch(error){page=null;el('currentChainCards').replaceChildren();el('currentBlockDetails').replaceChildren();el('currentBlockJson').textContent='No current-chain verification available.';el('currentChainStatus').textContent=error.message}finally{loading=false;controls()}
 }
 el('chainRefresh').onclick=()=>load();el('chainOlder').onclick=()=>load(page?.older_end);el('chainNewer').onclick=()=>load(page?.newer_end);el('chainCategory').onchange=render;
 el('chainGo').onclick=()=>{let number=el('chainNumber').value;if(number===''||!Number.isSafeInteger(Number(number))||Number(number)<0){el('currentChainStatus').textContent='Enter a valid nonnegative block number.';return}el('chainCategory').value='all';load(Number(number))};
 el('chainNumber').onkeydown=e=>{if(e.key==='Enter')el('chainGo').click()};controls();
 new MutationObserver(()=>{if(!el('adminApp').hidden)load()}).observe(el('adminApp'),{attributes:true,attributeFilter:['hidden']});
})();
