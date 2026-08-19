(function(){
  const statusLabels={inquiry:'Inquiry',requested:'Needs confirmation',confirmed:'Confirmed',arrived:'Guests arrived',completed:'Completed',cancelled:'Cancelled',declined:'Declined',no_show:'No show'};
  const inactiveStatuses=new Set(['cancelled','declined','no_show']);
  const formValue=(form,name,value)=>{if(form.elements[name])form.elements[name].value=value??''};
  const localDateTime=value=>value?String(value).slice(0,16):'';
  const money=value=>Number(value||0).toLocaleString(undefined,{style:'currency',currency:'EUR',maximumFractionDigits:0});

  function hospitalityPackageOptions(selected=''){
    return (state.hospitality?.packages||[]).filter(row=>row.active||row.id===selected).map(row=>`<option value="${esc(row.id)}" ${row.id===selected?'selected':''}>${esc(row.name)} · ${row.min_guests}–${row.max_guests} guests</option>`).join('');
  }

  async function loadHospitality(){
    if(!state.session?.permissions?.hospitality)return;
    state.hospitality=await api('api/v1/hospitality/dashboard');
    renderHospitality();
  }
  window.loadHospitality=loadHospitality;

  function reservationFilter(row){
    const filter=$('hospitalityStatusFilter')?.value||'active';
    if(filter==='all')return true;
    if(filter==='active')return !inactiveStatuses.has(row.status)&&row.status!=='completed';
    if(filter==='requested')return ['inquiry','requested'].includes(row.status);
    return row.status===filter;
  }

  function renderHospitality(){
    const data=state.hospitality;if(!data)return;
    const summary=data.summary||{};
    $('hospitalitySummary').innerHTML=`<article class="metric"><span>Upcoming</span><strong>${summary.upcoming||0}</strong><small>private experiences</small></article><article class="metric"><span>Needs confirmation</span><strong>${summary.awaiting_confirmation||0}</strong><small>inquiries and requests</small></article><article class="metric"><span>Confirmed guests</span><strong>${summary.confirmed_guests||0}</strong><small>one party at a time</small></article><article class="metric"><span>Quoted value</span><strong>${money(summary.quoted_revenue_eur)}</strong><small>${money(summary.deposits_eur)} deposits received</small></article>`;
    const rows=(data.reservations||[]).filter(reservationFilter),node=$('hospitalityBookings');
    node.classList.toggle('empty',!rows.length);
    node.innerHTML=rows.length?rows.map(row=>{const start=new Date(row.start_at),balance=Number(row.balance_due_eur||0),details=[row.dietary_restrictions&&'Dietary details',row.celebration_details&&'Celebration',row.guest_preferences&&'Preferences'].filter(Boolean);return`<article class="hospitality-booking status-${esc(row.status)}" data-hospitality-booking="${esc(row.id)}"><time><b>${start.toLocaleDateString(undefined,{month:'short',day:'numeric'})}</b><span>${start.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</span></time><div class="hospitality-booking-main"><div><span class="hospitality-status">${esc(statusLabels[row.status]||row.status)}</span><h3>${esc(row.guest_name)}</h3><p>${esc(row.package_name||'Custom private experience')} · ${row.guest_count} guest${Number(row.guest_count)===1?'':'s'}</p></div><small>${esc(row.confirmation_code)}${details.length?' · '+details.join(' · '):''}</small></div><div class="hospitality-booking-value"><strong>${money(row.quoted_total_eur)}</strong><small>${balance>0?`${money(balance)} due`:'settled / no balance'}</small><button type="button" class="secondary">Open</button></div></article>`}).join(''):'No reservations match this view.';
    node.querySelectorAll('[data-hospitality-booking]').forEach(card=>card.onclick=()=>openHospitalityBooking(card.dataset.hospitalityBooking));
    const todayKey=new Date().toISOString().slice(0,10),todayRows=(data.reservations||[]).filter(row=>String(row.start_at).slice(0,10)===todayKey&&!inactiveStatuses.has(row.status));
    $('hospitalityToday').innerHTML=todayRows.length?todayRows.map(row=>`<div><b>${esc(row.guest_name)} · ${new Date(row.start_at).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</b><span>${esc(row.package_name||'Private experience')} · ${row.guest_count} guests</span><small>${esc(row.dietary_restrictions||'No dietary restrictions recorded')}</small></div>`).join(''):'<p>No experience scheduled today.</p>';
    $('hospitalityPackages').innerHTML=(data.packages||[]).map(row=>`<button type="button" class="hospitality-package ${row.active?'':'inactive'}" data-hospitality-package="${esc(row.id)}"><span><b>${esc(row.name)}</b><small>${row.duration_minutes} min · ${row.min_guests}–${row.max_guests} guests</small></span><strong>${row.price_basis==='quote'?'Quote':row.price_basis==='per_person'?money(row.price_eur)+'/person':money(row.price_eur)}</strong></button>`).join('')||'<p>No packages configured.</p>';
    $('hospitalityPackages').querySelectorAll('[data-hospitality-package]').forEach(button=>button.onclick=()=>openHospitalityPackage(button.dataset.hospitalityPackage));
  }
  window.renderHospitality=renderHospitality;

  function openHospitalityBooking(id=''){
    const row=(state.hospitality?.reservations||[]).find(item=>item.id===id)||{},form=$('hospitalityBookingForm');
    form.reset();formValue(form,'id',row.id);formValue(form,'guest_name',row.guest_name);form.elements.package_id.innerHTML='<option value="">Choose package…</option>'+hospitalityPackageOptions(row.package_id);formValue(form,'package_id',row.package_id);formValue(form,'start_at',localDateTime(row.start_at));formValue(form,'guest_count',row.guest_count||2);formValue(form,'status',row.status||'inquiry');formValue(form,'preferred_language',row.preferred_language||'en');for(const name of ['guest_email','guest_phone','quoted_total_eur','deposit_received_eur','dietary_restrictions','celebration_details','guest_preferences','internal_notes'])formValue(form,name,row[name]);
    if(!row.start_at){const next=new Date(Date.now()+86400000);next.setHours(16,0,0,0);formValue(form,'start_at',localDateTime(next.toISOString()))}
    $('hospitalityBookingTitle').textContent=row.id?`${row.guest_name} · ${row.confirmation_code}`:'New private experience';
    const comm=$('hospitalityCommunication');comm.hidden=!row.id;comm.innerHTML=row.id?`<div><b>Guest communication</b><small>Messages send only when you press a button and remain in the audit history.</small></div><button type="button" data-hospitality-send="email" ${row.guest_email?'':'disabled'}>Email confirmation</button><button type="button" data-hospitality-send="whatsapp" ${row.guest_phone?'':'disabled'}>WhatsApp confirmation</button><button type="button" class="secondary" data-hospitality-send="phone">Record phone call</button>`:'';
    comm.querySelectorAll('[data-hospitality-send]').forEach(button=>button.onclick=()=>sendHospitalityCommunication(row.id,button.dataset.hospitalitySend,button));
    $('hospitalityBookingDialog').showModal();
  }
  window.openHospitalityBooking=openHospitalityBooking;

  function openHospitalityPackage(id=''){
    const row=(state.hospitality?.packages||[]).find(item=>item.id===id)||{},form=$('hospitalityPackageForm');form.reset();
    for(const name of ['id','name','experience_type','duration_minutes','min_guests','max_guests','price_basis','price_eur','deposit_eur','sort_order','description','inclusions'])formValue(form,name,row[name]);
    if(!row.id){formValue(form,'experience_type','tasting');formValue(form,'duration_minutes',90);formValue(form,'min_guests',1);formValue(form,'max_guests',6);formValue(form,'price_basis','quote');form.elements.active.checked=true}else form.elements.active.checked=Boolean(row.active);
    $('hospitalityPackageTitle').textContent=row.id?row.name:'New experience package';$('hospitalityPackageDialog').showModal();
  }

  async function saveHospitalityBooking(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id;delete data.id;for(const name of ['guest_count','quoted_total_eur','deposit_received_eur'])data[name]=Number(data[name]||0);const button=event.submitter;button.disabled=true;try{await api(id?`api/v1/hospitality/reservations/${encodeURIComponent(id)}`:'api/v1/hospitality/reservations',{method:id?'PUT':'POST',body:JSON.stringify(data)});form.closest('dialog').close();toast(id?'Reservation updated':'Reservation created');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function saveHospitalityPackage(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id;delete data.id;for(const name of ['duration_minutes','min_guests','max_guests','price_eur','deposit_eur','sort_order'])data[name]=Number(data[name]||0);data.active=form.elements.active.checked;const button=event.submitter;button.disabled=true;try{await api(id?`api/v1/hospitality/packages/${encodeURIComponent(id)}`:'api/v1/hospitality/packages',{method:id?'PUT':'POST',body:JSON.stringify(data)});form.closest('dialog').close();toast('Experience package saved');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function sendHospitalityCommunication(id,channel,button){const label=channel==='phone'?'Record this phone contact?':`Send the confirmation by ${channel}?`;if(!confirm(label))return;button.disabled=true;try{await api(`api/v1/hospitality/reservations/${encodeURIComponent(id)}/communication`,{method:'POST',body:JSON.stringify({channel})});toast(channel==='phone'?'Phone contact recorded':`Confirmation sent by ${channel}`);await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}

  const originalSetNavMode=setNavMode;
  setNavMode=function(mode,activate=false){
    const permissions=state.session?.permissions||{},canOperations=Boolean(permissions.operations_workspace),canHospitality=Boolean(permissions.hospitality),canAdmin=Boolean(permissions.admin);
    let chosen=mode;if(chosen==='admin'&&!canAdmin)chosen=canHospitality?'hospitality':'operations';if(chosen==='hospitality'&&!canHospitality)chosen=canOperations?'operations':'admin';if(chosen==='operations'&&!canOperations)chosen=canHospitality?'hospitality':'admin';
    document.body.classList.toggle('nav-admin-mode',chosen==='admin');document.body.classList.toggle('nav-hospitality-mode',chosen==='hospitality');document.body.classList.toggle('nav-operations-mode',chosen==='operations');document.querySelectorAll('[data-nav-mode]').forEach(button=>button.classList.toggle('active',button.dataset.navMode===chosen));try{localStorage.setItem('baiamonte-nav-mode',chosen)}catch{}
    if(activate){const selector=chosen==='admin'?'.tabs button[data-view="admin"]':chosen==='hospitality'?'.tabs button[data-view="hospitality"]':'.tabs button[data-view="today"]';activateViewButton(document.querySelector(`${selector}:not([hidden])`));}
  };
  window.setNavMode=setNavMode;

  const originalApplyAccess=applyAccess;
  applyAccess=function(){originalApplyAccess();const p=state.session?.permissions||{},hospitality=Boolean(p.hospitality),admin=Boolean(p.admin),operations=Boolean(p.operations_workspace);document.querySelectorAll('[data-hospitality]').forEach(node=>node.hidden=!hospitality);document.querySelector('[data-nav-mode="operations"]').hidden=!operations;document.querySelector('[data-nav-mode="hospitality"]').hidden=!hospitality;document.querySelector('[data-nav-mode="admin"]').hidden=!admin;$('navModeSwitch').hidden=[operations,hospitality,admin].filter(Boolean).length<2;if(hospitality&&!operations&&!admin)setNavMode('hospitality');};
  window.applyAccess=applyAccess;

  const originalActivateViewButton=activateViewButton;
  activateViewButton=function(button){originalActivateViewButton(button);if(button?.dataset.view==='hospitality'&&!state.hospitality)loadHospitality()};
  window.activateViewButton=activateViewButton;

  const originalLoadAll=loadAll;
  loadAll=async function(){if(!state.session)state.session=await api('api/v1/session');applyAccess();const p=state.session.permissions||{};if(p.hospitality&&!p.operations_workspace&&!p.admin){setNavMode('hospitality',true);await loadHospitality();return}return originalLoadAll()};
  window.loadAll=loadAll;

  const originalOpenAdminPerson=openAdminPerson;
  openAdminPerson=function(key){originalOpenAdminPerson(key);const form=$('personAccessForm'),person=(state.adminControl?.people_directory||[]).find(item=>item.key===key);if(!form)return;const select=form.elements.access_level;if(select&&!select.querySelector('[value="hospitality"]'))select.querySelector('[value="worker"]')?.insertAdjacentHTML('beforebegin','<option value="hospitality">Hospitality</option>');if(select&&person)select.value=person.access_level||'viewer';const username=form.elements.username;if(username&&person?.ha_user_id&&person?.username){username.readOnly=true;username.title='Managed by Home Assistant';}const header=form.querySelector('header small');if(header)header.textContent='Home Assistant is authoritative for name, username and identity. This profile assigns application access, estate role and approval responsibilities.'};
  window.openAdminPerson=openAdminPerson;

  $('hospitalityNewBooking')?.addEventListener('click',()=>openHospitalityBooking());$('hospitalityNewPackage')?.addEventListener('click',()=>openHospitalityPackage());$('hospitalityStatusFilter')?.addEventListener('change',renderHospitality);$('hospitalityBookingForm')?.addEventListener('submit',saveHospitalityBooking);$('hospitalityPackageForm')?.addEventListener('submit',saveHospitalityPackage);document.querySelectorAll('[data-close-hospitality]').forEach(button=>button.onclick=()=>button.closest('dialog').close());document.querySelectorAll('[data-close-hospitality-package]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
})();
