/* Presentation only: the existing server remains responsible for authorization. */
(() => {
  const admin = !!document.getElementById('adminApp');
  const role = admin ? 'Administrator' : 'Hospital';
  const paths = {
    overview:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    hospitals:'M5 21V5h14v16 M9 21v-4h6v4 M9 9h6 M12 6v6',
    training:'M4 17l5-6 4 3 7-10 M4 4v16h16',
    prediction:'M3 12h4l3-7 4 14 3-7h4',
    history:'M3 11a9 9 0 1 1 3 8 M3 4v7h7 M12 7v5l3 2',
    wallet:'M3 6h17v14H3z M3 6V3h14 M15 11h6v5h-6z',
    menu:'M4 6h16 M4 12h16 M4 18h16',
    client:'M4 3h16v13H4z M8 21h8 M12 16v5'
  };
  const icon = name => `<svg class="shell-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name]}"/></svg>`;
  const sidebar = document.createElement('aside');
  sidebar.id = 'appSidebar';sidebar.className = 'app-sidebar';
  sidebar.innerHTML = `<div class="sidebar-brand"><span class="brand-mark">F</span><div><div class="brand-name">Fed-Ledger</div><div class="brand-subtitle">Federated intelligence</div></div></div><div class="sidebar-label">${role} workspace</div><nav class="shell-nav" aria-label="${role} navigation"></nav><div class="sidebar-bottom"><strong>Local research environment</strong>ResNet-18 / FedProx<br><a href="${admin?'/hospital':'/admin'}">${admin?'Open hospital portal':'Administrator sign-in'} &rarr;</a></div>`;
  const bar = document.createElement('div');bar.className='app-topbar';
  bar.innerHTML=`<div class="top-left"><button class="menu-toggle" aria-label="Toggle navigation" aria-controls="appSidebar" aria-expanded="true">${icon('menu')}</button><div><div class="top-heading">${role} dashboard</div><div class="top-caption">Pneumonia research / ${admin?'Network coordination':'Hospital workspace'}</div></div></div><div class="top-right"><span class="environment-chip">Local prototype</span><span class="role-avatar" aria-label="${role}">${admin?'AD':'HP'}</span></div>`;
  const overlay=document.createElement('button');overlay.className='shell-overlay';overlay.setAttribute('aria-label','Close navigation');overlay.tabIndex=-1;
  document.body.prepend(sidebar,bar,overlay);
  const nav=sidebar.querySelector('nav'), toggle=bar.querySelector('button'), mobile=()=>matchMedia('(max-width:760px)').matches;
  const links=admin?[['campaignOverview','Overview','overview'],['hospitals','Hospitals','hospitals'],['roundOperations','Training campaigns','training'],['currentExplorer','Blockchain explorer','client'],['prediction','Model prediction','prediction'],['experimentHistory','Experiment history','history']]:
    [['workspace','My hospital','hospitals'],['clientWorkspace','Local client & data','client'],['participation','Participation','training'],['prediction','Model prediction','prediction']];
  function close(){document.body.classList.remove('mobile-nav-open');sync()}
  function sync(){const open=mobile()?document.body.classList.contains('mobile-nav-open'):!document.body.classList.contains('sidebar-collapsed');toggle.setAttribute('aria-expanded',String(open));sidebar.inert=!open}
  toggle.onclick=()=>{document.body.classList.toggle(mobile()?'mobile-nav-open':'sidebar-collapsed');sync()};
  overlay.onclick=close;document.addEventListener('keydown',e=>{if(e.key==='Escape'){close();toggle.focus()}});window.addEventListener('resize',sync);
  function render(){
    const loggedIn=admin?!document.getElementById('adminApp').hidden:!document.getElementById('workspace').hidden;
    const items=loggedIn?links.filter(([id])=>{const target=document.getElementById(id);return target&&!target.closest('[hidden]')}):[[admin?'adminLogin':'signIn','Sign in','wallet']];
    const key=String(loggedIn)+items.map(([id])=>id).join(',');if(nav.dataset.state===key)return;nav.dataset.state=key;nav.replaceChildren();
    for(const [id,label,name] of items){const a=document.createElement('a');a.href='#'+id;a.innerHTML=icon(name);a.append(document.createTextNode(label));
      a.onclick=e=>{const target=document.getElementById(id);if(!target)return;e.preventDefault();if(target.tagName==='DETAILS')target.open=true;
        nav.querySelectorAll('a').forEach(n=>{n.classList.remove('active');n.removeAttribute('aria-current')});a.classList.add('active');a.setAttribute('aria-current','location');target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});if(mobile())close()};
      nav.append(a)}
    nav.firstElementChild?.classList.add('active');
  }
  new MutationObserver(render).observe(document.getElementById(admin?'adminApp':'workspace'),{attributes:true,subtree:true,attributeFilter:['hidden']});
  render();sync();
})();
