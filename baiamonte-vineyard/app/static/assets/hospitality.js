(function(){
  const statusLabels={inquiry:'Inquiry',requested:'Needs confirmation',confirmed:'Confirmed',arrived:'Guests arrived',completed:'Completed',cancelled:'Cancelled',declined:'Declined',no_show:'No show'};
  const inactiveStatuses=new Set(['cancelled','declined','no_show']);
  const formValue=(form,name,value)=>{if(form.elements[name])form.elements[name].value=value??''};
  const localDateTime=value=>value?String(value).slice(0,16):'';
  const money=value=>Number(value||0).toLocaleString(undefined,{style:'currency',currency:'EUR',minimumFractionDigits:0,maximumFractionDigits:2});

  function hospitalityPackageOptions(selected=''){
    return (state.hospitality?.packages||[]).filter(row=>row.active||row.id===selected).map(row=>`<option value="${esc(row.id)}" ${row.id===selected?'selected':''}>${esc(row.name)} · ${row.min_guests}–${row.max_guests} guests</option>`).join('');
  }

  function hospitalityPartnerOptions(selected=''){
    return (state.hospitalityPartners?.partners||[]).filter(row=>row.active||row.id===selected).map(row=>`<option value="${esc(row.id)}" ${row.id===selected?'selected':''}>${esc(row.name)} · ${esc(String(row.partner_type||'partner').replaceAll('_',' '))}</option>`).join('');
  }

  async function loadHospitality(){
    if(!state.session?.permissions?.hospitality)return;
    [state.hospitality,state.hospitalityPartners]=await Promise.all([
      api('api/v1/hospitality/dashboard'),
      api(`api/v1/hospitality/partners?year=${encodeURIComponent(state.year||new Date().getFullYear())}`),
    ]);
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

  function showHospitalityPanel(panel='bookings'){
    document.querySelectorAll('[data-hospitality-panel-view]').forEach(node=>node.hidden=node.dataset.hospitalityPanelView!==panel);
    document.querySelectorAll('.tab-row-hospitality [data-hospitality-panel]').forEach(button=>button.classList.toggle('active',button.dataset.hospitalityPanel===panel));
    $('hospitalityNewBooking').hidden=panel!=='bookings';
    try{sessionStorage.setItem('baiamonte-hospitality-panel',panel)}catch{}
  }

  function inquiryFilter(row){
    const filter=$('hospitalityInquiryFilter')?.value||'active';
    if(filter==='all')return true;
    if(filter==='active')return ['new','responded'].includes(row.status);
    return row.status===filter;
  }

  function replyTemplate(row){
    const settings=state.hospitality?.settings||{},name=row.sender_name||'Guest',subject=row.subject||'Your inquiry';
    return {
      subject:String(settings.default_reply_subject||'Re: {original_subject}').replaceAll('{guest_name}',name).replaceAll('{original_subject}',subject),
      body:String(settings.default_reply_body||'Dear {guest_name},\n\nThank you for contacting Tenuta Baiamonte.').replaceAll('{guest_name}',name).replaceAll('{original_subject}',subject),
    };
  }

  function renderHospitality(){
    const data=state.hospitality;if(!data)return;
    const summary=data.summary||{};
    $('hospitalitySummary').innerHTML=`<article class="metric"><span>Upcoming</span><strong>${summary.upcoming||0}</strong><small>private experiences</small></article><article class="metric"><span>Needs confirmation</span><strong>${summary.awaiting_confirmation||0}</strong><small>inquiries and requests</small></article><article class="metric"><span>Confirmed guests</span><strong>${summary.confirmed_guests||0}</strong><small>one party at a time</small></article><article class="metric"><span>Quoted value</span><strong>${money(summary.quoted_revenue_eur)}</strong><small>${money(summary.deposits_eur)} deposits received</small></article>`;
    const rows=(data.reservations||[]).filter(reservationFilter),node=$('hospitalityBookings');
    node.classList.toggle('empty',!rows.length);
    node.innerHTML=rows.length?rows.map(row=>{const start=new Date(row.start_at),balance=Number(row.balance_due_eur||0),details=[row.partner_name&&`Partner: ${row.partner_name}`,row.dietary_restrictions&&'Dietary details',row.celebration_details&&'Celebration',row.guest_preferences&&'Preferences'].filter(Boolean);return`<article class="hospitality-booking status-${esc(row.status)}" data-hospitality-booking="${esc(row.id)}"><time><b>${start.toLocaleDateString(undefined,{month:'short',day:'numeric'})}</b><span>${start.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</span></time><div class="hospitality-booking-main"><div><span class="hospitality-status">${esc(statusLabels[row.status]||row.status)}</span><h3>${esc(row.guest_name)}</h3><p>${esc(row.package_name||'Custom private experience')} · ${row.guest_count} guest${Number(row.guest_count)===1?'':'s'}</p></div><small>${esc(row.confirmation_code)}${details.length?' · '+details.map(esc).join(' · '):''}</small></div><div class="hospitality-booking-value"><strong>${money(row.quoted_total_eur)}</strong><small>${balance>0?`${money(balance)} due`:'settled / no balance'}</small><button type="button" class="secondary">Open</button></div></article>`}).join(''):'No reservations match this view.';
    node.querySelectorAll('[data-hospitality-booking]').forEach(card=>card.onclick=()=>openHospitalityBooking(card.dataset.hospitalityBooking));
    const todayKey=new Date().toISOString().slice(0,10),todayRows=(data.reservations||[]).filter(row=>String(row.start_at).slice(0,10)===todayKey&&!inactiveStatuses.has(row.status));
    $('hospitalityToday').innerHTML=todayRows.length?todayRows.map(row=>`<div><b>${esc(row.guest_name)} · ${new Date(row.start_at).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</b><span>${esc(row.package_name||'Private experience')} · ${row.guest_count} guests</span><small>${esc(row.dietary_restrictions||'No dietary restrictions recorded')}</small></div>`).join(''):'<p>No experience scheduled today.</p>';
    $('hospitalityPackages').innerHTML=(data.packages||[]).map(row=>`<button type="button" class="hospitality-package ${row.active?'':'inactive'}" data-hospitality-package="${esc(row.id)}"><span><b>${esc(row.name)}</b><small>${row.duration_minutes} min · ${row.min_guests}–${row.max_guests} guests</small></span><strong>${row.price_basis==='quote'?'Quote':row.price_basis==='per_person'?money(row.price_eur)+'/person':money(row.price_eur)}</strong></button>`).join('')||'<p>No packages configured.</p>';
    $('hospitalityPackages').querySelectorAll('[data-hospitality-package]').forEach(button=>button.onclick=()=>openHospitalityPackage(button.dataset.hospitalityPackage));
    const inquiryRows=(data.inquiries||[]).filter(inquiryFilter),inquiryNode=$('hospitalityInquiries');
    inquiryNode.classList.toggle('empty',!inquiryRows.length);
    inquiryNode.innerHTML=inquiryRows.length?inquiryRows.map(row=>`<article class="hospitality-inquiry status-${esc(row.status)}" data-hospitality-inquiry="${esc(row.id)}"><span class="hospitality-inquiry-icon">${row.status==='converted'?'✓':row.status==='responded'?'↗':'✉'}</span><div><span class="hospitality-status">${esc(row.status)}</span><h3>${esc(row.sender_name||row.sender_address||'Guest')}</h3><p>${esc(row.subject||'No subject')}</p><small>${esc(String(row.message_text||'').replace(/\s+/g,' ').slice(0,180))}</small></div><time>${row.received_at?new Date(row.received_at).toLocaleString():''}</time><button type="button" class="secondary">Open</button></article>`).join(''):'No guest inquiries match this view.';
    inquiryNode.querySelectorAll('[data-hospitality-inquiry]').forEach(card=>card.onclick=()=>openHospitalityInquiry(card.dataset.hospitalityInquiry));
    const settings=data.settings||{},settingsForm=$('hospitalitySettingsForm');
    if(settingsForm&&!settingsForm.matches(':focus-within')){formValue(settingsForm,'inbound_labels',(settings.inbound_labels||[]).join('\n'));formValue(settingsForm,'inbound_subjects',(settings.inbound_subjects||[]).join('\n'));formValue(settingsForm,'default_reply_subject',settings.default_reply_subject);formValue(settingsForm,'default_reply_body',settings.default_reply_body)}
    renderHospitalityPartners();
  }
  window.renderHospitality=renderHospitality;

  function openHospitalityBooking(id='',prefill={}){
    const row=(state.hospitality?.reservations||[]).find(item=>item.id===id)||prefill||{},form=$('hospitalityBookingForm');
    form.reset();formValue(form,'id',row.id);formValue(form,'inquiry_id',row.inquiry_id);formValue(form,'guest_name',row.guest_name);form.elements.package_id.innerHTML='<option value="">Choose package…</option>'+hospitalityPackageOptions(row.package_id);formValue(form,'package_id',row.package_id);form.elements.partner_id.innerHTML='<option value="">Direct booking · no partner</option>'+hospitalityPartnerOptions(row.partner_id);formValue(form,'partner_id',row.partner_id);formValue(form,'start_at',localDateTime(row.start_at));formValue(form,'guest_count',row.guest_count||2);formValue(form,'status',row.status||'inquiry');formValue(form,'preferred_language',row.preferred_language||'en');for(const name of ['guest_email','guest_phone','quoted_total_eur','deposit_received_eur','partner_referral_code','commission_type','commission_value','dietary_restrictions','celebration_details','guest_preferences','internal_notes'])formValue(form,name,row[name]);
    if(!row.start_at){const next=new Date(Date.now()+86400000);next.setHours(16,0,0,0);formValue(form,'start_at',localDateTime(next.toISOString()))}
    $('hospitalityBookingTitle').textContent=row.id?`${row.guest_name} · ${row.confirmation_code}`:'New private experience';
    const comm=$('hospitalityCommunication');comm.hidden=!row.id;comm.innerHTML=row.id?`<div><b>Guest communication</b><small>Messages send only when you press a button and remain in the audit history.</small></div><button type="button" data-hospitality-send="email" ${row.guest_email?'':'disabled'}>Email confirmation</button><button type="button" data-hospitality-send="whatsapp" ${row.guest_phone?'':'disabled'}>WhatsApp confirmation</button><button type="button" class="secondary" data-hospitality-send="phone">Record phone call</button>`:'';
    comm.querySelectorAll('[data-hospitality-send]').forEach(button=>button.onclick=()=>sendHospitalityCommunication(row.id,button.dataset.hospitalitySend,button));
    const deleteButton=$('hospitalityDeleteBooking');deleteButton.hidden=!row.id;deleteButton.onclick=row.id?()=>deleteHospitalityBooking(row.id):null;
    $('hospitalityBookingDialog').showModal();
  }
  window.openHospitalityBooking=openHospitalityBooking;

  function openHospitalityInquiry(id){
    const row=(state.hospitality?.inquiries||[]).find(item=>item.id===id);if(!row)return;
    const form=$('hospitalityInquiryForm'),template=replyTemplate(row);form.reset();formValue(form,'id',row.id);formValue(form,'response_subject',row.response_subject||template.subject);formValue(form,'response_body',row.response_body||template.body);formValue(form,'status',row.status||'new');formValue(form,'internal_notes',row.internal_notes);
    $('hospitalityInquiryTitle').textContent=row.sender_name||row.sender_address||'Guest request';$('hospitalityInquiryMeta').textContent=`${row.sender_address||'No reply address'} · ${row.received_at?new Date(row.received_at).toLocaleString():''}`;$('hospitalityInquiryMessage').textContent=row.message_text||'No message body was included.';
    $('hospitalityConvertInquiry').disabled=row.status==='converted';$('hospitalityInquiryDialog').showModal();
  }

  async function saveInquiryState(id,status,notes){await api(`api/v1/hospitality/inquiries/${encodeURIComponent(id)}`,{method:'PUT',body:JSON.stringify({status,internal_notes:notes})});await loadHospitality()}
  async function respondHospitalityInquiry(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),button=event.submitter;if(!confirm(`Send this reply to the guest by email?`))return;button.disabled=true;try{await api(`api/v1/hospitality/inquiries/${encodeURIComponent(data.id)}/response`,{method:'POST',body:JSON.stringify({subject:data.response_subject,body:data.response_body})});form.closest('dialog').close();toast('Guest reply sent');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function closeHospitalityInquiry(){const form=$('hospitalityInquiryForm'),data=Object.fromEntries(new FormData(form).entries()),button=$('hospitalityCloseInquiry');button.disabled=true;try{await saveInquiryState(data.id,data.status,data.internal_notes);form.closest('dialog').close();toast('Inquiry updated')}catch(error){toast(error.message)}finally{button.disabled=false}}
  function convertHospitalityInquiry(){const form=$('hospitalityInquiryForm'),data=Object.fromEntries(new FormData(form).entries()),row=(state.hospitality?.inquiries||[]).find(item=>item.id===data.id);if(!row)return;form.closest('dialog').close();openHospitalityBooking('',{inquiry_id:row.id,guest_name:row.sender_name||row.sender_address,guest_email:row.sender_address,status:'requested',internal_notes:`Converted from Gmail inquiry: ${row.subject||''}`})}
  async function deleteHospitalityInquiry(){const id=$('hospitalityInquiryForm').elements.id.value;if(!confirm('Delete this guest inquiry? The deletion remains in the audit history.'))return;try{await api(`api/v1/hospitality/inquiries/${encodeURIComponent(id)}`,{method:'DELETE'});$('hospitalityInquiryDialog').close();toast('Inquiry deleted');await loadHospitality()}catch(error){toast(error.message)}}

  async function deleteHospitalityBooking(id){if(!confirm('Delete this reservation? Its inquiry, if any, will return to the responded queue and the deletion remains audited.'))return;try{await api(`api/v1/hospitality/reservations/${encodeURIComponent(id)}`,{method:'DELETE'});$('hospitalityBookingDialog').close();toast('Reservation deleted');await loadHospitality()}catch(error){toast(error.message)}}

  function openHospitalityPackage(id=''){
    const row=(state.hospitality?.packages||[]).find(item=>item.id===id)||{},form=$('hospitalityPackageForm');form.reset();
    for(const name of ['id','name','experience_type','duration_minutes','min_guests','max_guests','price_basis','price_eur','deposit_eur','sort_order','description','inclusions'])formValue(form,name,row[name]);
    if(!row.id){formValue(form,'experience_type','tasting');formValue(form,'duration_minutes',90);formValue(form,'min_guests',1);formValue(form,'max_guests',6);formValue(form,'price_basis','quote');form.elements.active.checked=true}else form.elements.active.checked=Boolean(row.active);
    $('hospitalityPackageTitle').textContent=row.id?row.name:'New experience package';$('hospitalityPackageDialog').showModal();
  }

  async function saveHospitalityBooking(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id;delete data.id;if(data.inquiry_id)data.source='gmail inquiry';else delete data.inquiry_id;for(const name of ['guest_count','quoted_total_eur','deposit_received_eur'])data[name]=Number(data[name]||0);if(data.commission_value!=='')data.commission_value=Number(data.commission_value);else delete data.commission_value;if(!data.partner_id){data.partner_id='';data.partner_referral_code='';delete data.commission_type;delete data.commission_value}const button=event.submitter;button.disabled=true;try{await api(id?`api/v1/hospitality/reservations/${encodeURIComponent(id)}`:'api/v1/hospitality/reservations',{method:id?'PUT':'POST',body:JSON.stringify(data)});form.closest('dialog').close();toast(id?'Reservation updated':'Reservation created');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function saveHospitalityPackage(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id;delete data.id;for(const name of ['duration_minutes','min_guests','max_guests','price_eur','deposit_eur','sort_order'])data[name]=Number(data[name]||0);data.active=form.elements.active.checked;const button=event.submitter;button.disabled=true;try{await api(id?`api/v1/hospitality/packages/${encodeURIComponent(id)}`:'api/v1/hospitality/packages',{method:id?'PUT':'POST',body:JSON.stringify(data)});form.closest('dialog').close();toast('Experience package saved');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function sendHospitalityCommunication(id,channel,button){const label=channel==='phone'?'Record this phone contact?':`Send the confirmation by ${channel}?`;if(!confirm(label))return;button.disabled=true;try{await api(`api/v1/hospitality/reservations/${encodeURIComponent(id)}/communication`,{method:'POST',body:JSON.stringify({channel})});toast(channel==='phone'?'Phone contact recorded':`Confirmation sent by ${channel}`);await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function saveHospitalitySettings(event){event.preventDefault();const form=event.currentTarget,button=event.submitter,data=Object.fromEntries(new FormData(form).entries());data.inbound_labels=String(data.inbound_labels||'').split(/\r?\n/).map(value=>value.trim()).filter(Boolean);data.inbound_subjects=String(data.inbound_subjects||'').split(/\r?\n/).map(value=>value.trim()).filter(Boolean);button.disabled=true;try{await api('api/v1/hospitality/settings',{method:'PUT',body:JSON.stringify(data)});toast('Hospitality email routing saved');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function checkHospitalityInbox(){const button=$('hospitalityCheckInbox');button.disabled=true;button.textContent='Checking Gmail…';try{const result=await api('api/v1/hospitality/inquiries/sync',{method:'POST',body:'{}'});toast(`${Number(result.downloaded||0)} email item${Number(result.downloaded||0)===1?'':'s'} downloaded · ${Number(result.routed||0)} routed`);await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false;button.textContent='Check Gmail now'}}

  function commissionStatus(row){
    return {estimated:'Estimated',due:'Due for review',approved:'Ready to pay',partially_paid:'Partially paid',paid:'Paid',void:'Void'}[row.status]||row.status;
  }

  function renderHospitalityPartners(){
    const data=state.hospitalityPartners||{},summary=data.summary||{};
    const summaryNode=$('hospitalityPartnerSummary');
    if(summaryNode)summaryNode.innerHTML=`<article class="metric"><span>Estimated</span><strong>${money(summary.estimated_eur)}</strong><small>not yet approved</small></article><article class="metric"><span>Due</span><strong>${money(summary.due_eur)}</strong><small>needs commission review</small></article><article class="metric"><span>Ready to pay</span><strong>${money(summary.ready_to_pay_eur)}</strong><small>approved and outstanding</small></article><article class="metric"><span>Paid</span><strong>${money(summary.paid_eur)}</strong><small>${data.year||state.year} payments</small></article>`;
    const partners=data.partners||[],partnerNode=$('hospitalityPartners');
    if(partnerNode){partnerNode.classList.toggle('empty',!partners.length);partnerNode.innerHTML=partners.length?partners.map(row=>`<button type="button" class="hospitality-partner-card" data-hospitality-partner="${esc(row.id)}"><span><b>${esc(row.name)}</b><small>${esc(String(row.partner_type||'partner').replaceAll('_',' '))}${row.contact_name?' · '+esc(row.contact_name):''}</small></span><span><strong>${money(row.earned_eur)}</strong><small>${Number(row.reservation_count||0)} booking${Number(row.reservation_count||0)===1?'':'s'} · ${money(row.paid_eur)} paid</small></span><i class="status-dot ${row.active?'good':'muted'}"></i></button>`).join(''):'No partners yet.';partnerNode.querySelectorAll('[data-hospitality-partner]').forEach(button=>button.onclick=()=>openHospitalityPartner(button.dataset.hospitalityPartner))}
    const commissions=data.commissions||[],queueNode=$('hospitalityCommissionQueue');
    if(queueNode){queueNode.classList.toggle('empty',!commissions.length);queueNode.innerHTML=commissions.length?commissions.map(row=>`<button type="button" class="hospitality-commission-row status-${esc(row.status)}" data-hospitality-commission="${esc(row.id)}"><span><b>${esc(row.partner_name)}</b><small>${esc(row.confirmation_code)} · ${esc(row.guest_name)} · ${new Date(row.start_at).toLocaleDateString()}</small></span><span class="hospitality-commission-amount"><b>${money(row.commission_amount_eur)}</b><small>${money(row.balance_eur)} remaining</small></span><span class="hospitality-status">${esc(commissionStatus(row))}</span></button>`).join(''):'No partner commissions yet.';queueNode.querySelectorAll('[data-hospitality-commission]').forEach(button=>button.onclick=()=>openHospitalityCommission(button.dataset.hospitalityCommission))}
    const payments=data.payments||[],paymentNode=$('hospitalityPartnerPayments');
    if(paymentNode){paymentNode.classList.toggle('empty',!payments.length);paymentNode.innerHTML=payments.length?payments.slice(0,20).map(row=>`<div class="hospitality-payment-row"><span><b>${esc(row.partner_name)}</b><small>${esc(row.confirmation_code)} · ${esc(row.method||'payment')}${row.reference?' · '+esc(row.reference):''}</small></span><time>${new Date(`${row.paid_on}T12:00:00`).toLocaleDateString()}</time><strong>${money(row.amount_eur)}</strong></div>`).join(''):'No partner payments yet.'}
  }

  function openHospitalityPartner(id=''){
    const row=(state.hospitalityPartners?.partners||[]).find(item=>item.id===id)||{},form=$('hospitalityPartnerForm');form.reset();
    for(const name of ['id','name','partner_type','contact_name','email','phone','tax_id','default_commission_type','default_commission_value','payment_terms_days','payment_details','notes'])formValue(form,name,row[name]);
    if(!row.id){formValue(form,'partner_type','other');formValue(form,'default_commission_type','percentage');formValue(form,'default_commission_value',10);formValue(form,'payment_terms_days',30);form.elements.active.checked=true}else form.elements.active.checked=Boolean(row.active);
    $('hospitalityPartnerTitle').textContent=row.id?row.name:'New hospitality partner';$('hospitalityPartnerDialog').showModal();
  }

  async function saveHospitalityPartner(event){
    event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id,button=event.submitter;delete data.id;data.active=form.elements.active.checked;data.default_commission_value=Number(data.default_commission_value||0);data.payment_terms_days=Number(data.payment_terms_days||0);button.disabled=true;
    try{await api(id?`api/v1/hospitality/partners/${encodeURIComponent(id)}`:'api/v1/hospitality/partners',{method:id?'PUT':'POST',body:JSON.stringify(data)});form.closest('dialog').close();toast(id?'Partner updated':'Partner created');await loadHospitality()}catch(error){toast(error.message)}finally{button.disabled=false}
  }

  function renderCommissionPayments(row){
    const node=$('hospitalityPartnerPaymentList'),payments=row.payments||[];node.classList.toggle('empty',!payments.length);node.innerHTML=payments.length?payments.map(payment=>`<div class="hospitality-payment-row"><span><b>${money(payment.amount_eur)} · ${esc(String(payment.method||'payment').replaceAll('_',' '))}</b><small>${new Date(`${payment.paid_on}T12:00:00`).toLocaleDateString()}${payment.reference?' · '+esc(payment.reference):''}${payment.notes?' · '+esc(payment.notes):''}</small></span><span class="row-actions"><button type="button" class="secondary compact" data-edit-partner-payment="${esc(payment.id)}">Edit</button><button type="button" class="danger compact" data-delete-partner-payment="${esc(payment.id)}">Delete</button></span></div>`).join(''):'No payments recorded.';
    node.querySelectorAll('[data-edit-partner-payment]').forEach(button=>button.onclick=()=>editHospitalityPartnerPayment(button.dataset.editPartnerPayment));node.querySelectorAll('[data-delete-partner-payment]').forEach(button=>button.onclick=()=>deleteHospitalityPartnerPayment(button.dataset.deletePartnerPayment));
  }

  async function openHospitalityCommission(id){
    try{const row=await api(`api/v1/hospitality/partner-commissions/${encodeURIComponent(id)}`);state.hospitalityCommission=row;const form=$('hospitalityCommissionForm'),paymentForm=$('hospitalityPartnerPaymentForm');form.reset();formValue(form,'id',row.id);formValue(form,'amount_eur',row.commission_amount_eur);formValue(form,'due_on',row.due_date);formValue(form,'status',['partially_paid','paid'].includes(row.status)?'approved':row.status);formValue(form,'notes',row.notes);paymentForm.reset();formValue(paymentForm,'commission_id',row.id);formValue(paymentForm,'paid_on',new Date().toISOString().slice(0,10));formValue(paymentForm,'amount_eur',row.balance_eur);$('hospitalityCancelPaymentEdit').hidden=true;$('hospitalityCommissionTitle').textContent=`${row.partner_name} · ${money(row.commission_amount_eur)}`;$('hospitalityCommissionMeta').textContent=`${row.confirmation_code} · ${row.guest_name} · ${money(row.paid_eur)} paid · ${money(row.balance_eur)} remaining`;renderCommissionPayments(row);const dialog=$('hospitalityCommissionDialog');if(!dialog.open)dialog.showModal()}catch(error){toast(error.message)}
  }

  async function saveHospitalityCommission(event){
    event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),id=data.id,button=event.submitter;const payload={commission_amount_eur:Number(data.amount_eur||0),due_date:data.due_on||null,status:data.status,notes:data.notes};button.disabled=true;try{const row=await api(`api/v1/hospitality/partner-commissions/${encodeURIComponent(id)}`,{method:'PUT',body:JSON.stringify(payload)});state.hospitalityCommission=row;toast('Commission review saved');await loadHospitality();await openHospitalityCommission(id)}catch(error){toast(error.message)}finally{button.disabled=false}
  }

  function editHospitalityPartnerPayment(id){
    const row=(state.hospitalityCommission?.payments||[]).find(item=>item.id===id);if(!row)return;const form=$('hospitalityPartnerPaymentForm');for(const name of ['payment_id','amount_eur','paid_on','method','reference','notes'])formValue(form,name,row[name]);$('hospitalityCancelPaymentEdit').hidden=false;form.scrollIntoView({behavior:'smooth',block:'center'});
  }

  function cancelHospitalityPartnerPaymentEdit(){const form=$('hospitalityPartnerPaymentForm'),row=state.hospitalityCommission||{};form.reset();formValue(form,'commission_id',row.id);formValue(form,'paid_on',new Date().toISOString().slice(0,10));formValue(form,'amount_eur',row.balance_eur);$('hospitalityCancelPaymentEdit').hidden=true}

  async function saveHospitalityPartnerPayment(event){
    event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form).entries()),commissionId=data.commission_id,paymentId=data.payment_id,button=event.submitter;delete data.commission_id;delete data.payment_id;data.amount_eur=Number(data.amount_eur||0);button.disabled=true;try{await api(paymentId?`api/v1/hospitality/partner-commissions/${encodeURIComponent(commissionId)}/payments/${encodeURIComponent(paymentId)}`:`api/v1/hospitality/partner-commissions/${encodeURIComponent(commissionId)}/payments`,{method:paymentId?'PUT':'POST',body:JSON.stringify(data)});toast(paymentId?'Partner payment updated':'Partner payment recorded');await loadHospitality();await openHospitalityCommission(commissionId)}catch(error){toast(error.message)}finally{button.disabled=false}
  }

  async function deleteHospitalityPartnerPayment(id){
    if(!confirm('Delete this partner payment? The deletion remains in the audit history.'))return;const commissionId=state.hospitalityCommission?.id;try{await api(`api/v1/hospitality/partner-payments/${encodeURIComponent(id)}`,{method:'DELETE'});toast('Partner payment deleted');await loadHospitality();if(commissionId)await openHospitalityCommission(commissionId)}catch(error){toast(error.message)}
  }

  function renderPartnerFinance(){
    const data=state.finance?.partner_commissions||{},summary=data.summary||{},node=$('financePartnerCommissionSummary'),queue=$('financePartnerCommissionQueue');if(!node||!queue)return;
    node.innerHTML=`<article class="metric"><span>Partner payable</span><strong>${money(summary.outstanding_eur)}</strong><small>due and approved</small></article><article class="metric"><span>Ready to pay</span><strong>${money(summary.ready_to_pay_eur)}</strong><small>approved balance</small></article><article class="metric"><span>Paid</span><strong>${money(summary.paid_eur)}</strong><small>${state.year} partner payments</small></article>`;
    const rows=data.queue||[];queue.classList.toggle('empty',!rows.length);queue.innerHTML=rows.length?rows.map(row=>`<div class="finance-document-row"><span class="list-icon">⇄</span><div><b>${esc(row.partner_name)}</b><small>${esc(row.confirmation_code)} · ${esc(row.guest_name)} · ${esc(commissionStatus(row))}</small></div><time>${row.due_date?new Date(`${row.due_date}T12:00:00`).toLocaleDateString():'No due date'}</time><strong>${money(row.balance_eur)}</strong></div>`).join(''):'No partner commissions due.';
  }

  const originalRenderFinance=window.renderFinance;
  window.renderFinance=function(){originalRenderFinance?.();renderPartnerFinance()};

  const originalSetNavMode=setNavMode;
  function storedHospitalityPanel(){try{return sessionStorage.getItem('baiamonte-hospitality-panel')||'bookings'}catch{return'bookings'}}
  function storedEnologyPanel(){try{return sessionStorage.getItem('baiamonte-enology-panel')||'overview'}catch{return'overview'}}
  function showEnologyPanel(panel='overview'){
    const selected=['overview','records','labels'].includes(panel)?panel:'overview',view=$('view-cellar');if(!view)return;
    view.querySelectorAll('[data-enology-panel-content]').forEach(node=>node.hidden=selected==='overview'?node.dataset.enologyPanelContent!=='overview':node.dataset.enologyPanelContent!=='controls');
    view.querySelectorAll('[data-enology-task]').forEach(node=>node.hidden=selected==='overview'||node.dataset.enologyTask!==selected);
    view.querySelectorAll('[data-enology-task-link]').forEach(node=>node.hidden=selected==='overview'||node.dataset.enologyTaskLink!==selected);
    const title=$('enologyControlTitle');if(title)title.textContent=selected==='labels'?'Labels & dedicated displays':'Tank records & cellar controls';
    document.querySelectorAll('[data-enology-panel]').forEach(button=>button.classList.toggle('active',button.dataset.enologyPanel===selected));try{sessionStorage.setItem('baiamonte-enology-panel',selected)}catch{}
  }
  setNavMode=function(mode,activate=false){
    const p=state.session?.permissions||{},operations=Boolean(p.operations_workspace),allowed={operations,agronomy:operations,enology:operations,hospitality:Boolean(p.hospitality),admin:Boolean(p.admin)};
    let chosen=allowed[mode]?mode:allowed.operations?'operations':allowed.hospitality?'hospitality':'admin';
    ['operations','agronomy','enology','hospitality','admin'].forEach(name=>document.body.classList.toggle(`nav-${name}-mode`,chosen===name));document.querySelectorAll('[data-nav-mode]').forEach(button=>button.classList.toggle('active',button.dataset.navMode===chosen));try{localStorage.setItem('baiamonte-nav-mode',chosen)}catch{}
    if(activate){const selector=chosen==='admin'?'.tabs button[data-view="admin"]':chosen==='hospitality'?`.tabs button[data-hospitality-panel="${CSS.escape(storedHospitalityPanel())}"]`:chosen==='agronomy'?'.tabs button[data-view="agronomy"]':chosen==='enology'?`.tabs button[data-enology-panel="${CSS.escape(storedEnologyPanel())}"]`:'.tabs button[data-view="today"]';activateViewButton(document.querySelector(`${selector}:not([hidden])`));}
  };
  window.setNavMode=setNavMode;

  const originalApplyAccess=applyAccess;
  applyAccess=function(){originalApplyAccess();const p=state.session?.permissions||{},hospitality=Boolean(p.hospitality),admin=Boolean(p.admin),operations=Boolean(p.operations_workspace);document.querySelectorAll('[data-hospitality]').forEach(node=>node.hidden=!hospitality);for(const name of ['operations','agronomy','enology'])document.querySelector(`[data-nav-mode="${name}"]`).hidden=!operations;document.querySelector('[data-nav-mode="hospitality"]').hidden=!hospitality;document.querySelector('[data-nav-mode="admin"]').hidden=!admin;$('navModeSwitch').hidden=[operations&&'operations',operations&&'agronomy',operations&&'enology',hospitality&&'hospitality',admin&&'admin'].filter(Boolean).length<2;if(hospitality&&!operations&&!admin)setNavMode('hospitality');};
  window.applyAccess=applyAccess;

  const originalActivateViewButton=activateViewButton;
  activateViewButton=function(button){originalActivateViewButton(button);if(button?.dataset.view==='hospitality'){showHospitalityPanel(button.dataset.hospitalityPanel||'bookings');if(!state.hospitality)loadHospitality()}if(button?.dataset.view==='cellar')showEnologyPanel(button.dataset.enologyPanel||storedEnologyPanel())};
  window.activateViewButton=activateViewButton;

  const originalLoadAll=loadAll;
  loadAll=async function(){if(!state.session)state.session=await api('api/v1/session');applyAccess();const p=state.session.permissions||{};if(p.hospitality&&!p.operations_workspace&&!p.admin){setNavMode('hospitality',true);await loadHospitality();return}return originalLoadAll()};
  window.loadAll=loadAll;

  const originalOpenAdminPerson=openAdminPerson;
  openAdminPerson=function(key){originalOpenAdminPerson(key);const form=$('personAccessForm'),person=(state.adminControl?.people_directory||[]).find(item=>item.key===key);if(!form)return;const select=form.elements.access_level;if(select&&!select.querySelector('[value="hospitality"]'))select.querySelector('[value="worker"]')?.insertAdjacentHTML('beforebegin','<option value="hospitality">Hospitality</option>');if(select&&person)select.value=person.access_level||'viewer';const username=form.elements.username;if(username&&person?.ha_user_id&&person?.username){username.readOnly=true;username.title='Managed by Home Assistant';}const header=form.querySelector('header small');if(header)header.textContent='Home Assistant is authoritative for name, username and identity. This profile assigns application access, estate role and approval responsibilities.'};
  window.openAdminPerson=openAdminPerson;

  $('hospitalityNewBooking')?.addEventListener('click',()=>openHospitalityBooking());
  $('hospitalityNewPackage')?.addEventListener('click',()=>openHospitalityPackage());
  $('hospitalityNewPartner')?.addEventListener('click',()=>openHospitalityPartner());
  $('hospitalityStatusFilter')?.addEventListener('change',renderHospitality);
  $('hospitalityInquiryFilter')?.addEventListener('change',renderHospitality);
  $('hospitalityCheckInbox')?.addEventListener('click',checkHospitalityInbox);
  $('hospitalityBookingForm')?.addEventListener('submit',saveHospitalityBooking);
  $('hospitalityPackageForm')?.addEventListener('submit',saveHospitalityPackage);
  $('hospitalityPartnerForm')?.addEventListener('submit',saveHospitalityPartner);
  $('hospitalityCommissionForm')?.addEventListener('submit',saveHospitalityCommission);
  $('hospitalityPartnerPaymentForm')?.addEventListener('submit',saveHospitalityPartnerPayment);
  $('hospitalityCancelPaymentEdit')?.addEventListener('click',cancelHospitalityPartnerPaymentEdit);
  $('hospitalitySettingsForm')?.addEventListener('submit',saveHospitalitySettings);
  $('hospitalityInquiryForm')?.addEventListener('submit',respondHospitalityInquiry);
  $('hospitalityCloseInquiry')?.addEventListener('click',closeHospitalityInquiry);
  $('hospitalityConvertInquiry')?.addEventListener('click',convertHospitalityInquiry);
  $('hospitalityDeleteInquiry')?.addEventListener('click',deleteHospitalityInquiry);
  document.querySelectorAll('[data-close-hospitality]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
  document.querySelectorAll('[data-close-hospitality-package],[data-close-hospitality-inquiry]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
  showHospitalityPanel(storedHospitalityPanel());
  showEnologyPanel(storedEnologyPanel());
})();
