/* Personalized contractor layer on the private worker portal. */
(function(){
  const originalRender=window.renderWorkerPortal;
  const money=value=>typeof eur==='function'?eur(Number(value||0)):`€${Number(value||0).toFixed(2)}`;
  const when=value=>value?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'—';
  const statusLabel=value=>String(value||'verification_needed').replaceAll('_',' ');
  function metric(label,value,detail){return `<article><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail||'')}</small></article>`}
  function renderContractorPortal(){
    const data=state.workerPortal||{},overview=document.getElementById('contractorOverview');
    if(!overview)return;
    const contractor=data.portal_mode==='contractor';
    overview.hidden=!contractor;
    document.body.classList.toggle('contractor-only',contractor);
    if(!contractor)return;
    const delivery=data.water_delivery||{},latest=delivery.latest_delivery||{},totals=data.totals||{},deliveries=delivery.deliveries||[],jobs=delivery.payment_queue||[];
    document.querySelector('.worker-hero .eyebrow').textContent='TENUTA BAIAMONTE · CONTRACTOR';
    document.getElementById('contractorRole').textContent=data.estate_role||'Contractor';
    document.getElementById('contractorOverviewTitle').textContent=`${data.worker_name}'s deliveries, jobs & pay`;
    document.getElementById('contractorOverviewNote').textContent='Personalized from your signed-in Home Assistant account. Other workers and contractors are not shown.';
    document.getElementById('contractorMetrics').innerHTML=[
      metric('Confirmed water deliveries',String(delivery.confirmed_deliveries||0),`5,000 L each · ${Number(delivery.pending_claims||0)} awaiting evidence`),
      metric('Approved due',money(totals.year_due_pay),'Ready for payment'),
      metric('Verification hold',money(totals.year_verification_hold_pay),'Price or evidence review'),
      metric('Paid this year',money(totals.year_paid_pay),'Recorded payments'),
      metric('Latest cistern rise',latest.level_increase_pct==null?'—':`${fmt(latest.level_increase_pct)} points`,latest.completed_at?when(latest.completed_at):'No confirmed delivery'),
    ].join('');
    document.getElementById('contractorDeliveries').innerHTML=deliveries.length?deliveries.slice(0,12).map(row=>`<div class="contractor-row"><span class="contractor-row-icon">💧</span><div><b>${esc(when(row.completed_at))} · ${fmt(row.delivery_volume_l||delivery.standard_delivery_l||5000)} L</b><small>${row.status==='candidate'?'Reported once · awaiting camera and cistern evidence':`${Number(row.camera_count||0)} cameras · ${Number(row.observation_count||0)} observations · ${row.level_increase_pct==null?'level change unavailable':`${fmt(row.level_increase_pct)}-point cistern rise`}${row.calibration_eligible?' · liters calibration':''}`}</small></div><em>${row.status==='candidate'?'Pending':`${fmt(row.confidence_pct||0)}%`}</em></div>`).join(''):'<div class="empty">No water deliveries reported yet.</div>';
    document.getElementById('contractorJobs').innerHTML=jobs.length?jobs.slice(0,15).map(row=>`<div class="contractor-row"><span class="contractor-row-icon">🚚</span><div><b>${esc(String(row.created_at||'').slice(0,10)||'Water delivery')}</b><small>${esc(statusLabel(row.status))}${row.notes?` · ${esc(row.notes)}`:''}</small></div><strong>${row.amount_eur==null?'Price review':money(row.amount_eur)}</strong></div>`).join(''):'<div class="empty">No delivery payment jobs yet.</div>';
    const workSummary=document.querySelector('.worker-work-card summary small');
    if(workSummary)workSummary.textContent='Current estate priorities · Priorità attuali';
    bindContractorForm('contractorWorkItemForm','contractorWorkItemResult','api/v1/worker-portal/work-items','Added to the work plan for estate review.');
    bindContractorForm('contractorDeliveryClaimForm','contractorDeliveryClaimResult','api/v1/worker-portal/water-delivery-claims','Delivery reported once. Automatic evidence will update this same record.',true);
  }
  function bindContractorForm(formId,resultId,path,success,delivery=false){
    const form=document.getElementById(formId);if(!form||form.dataset.bound)return;form.dataset.bound='true';
    if(delivery&&!form.elements.service_at.value){const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000);form.elements.service_at.value=now.toISOString().slice(0,16)}
    form.onsubmit=async event=>{event.preventDefault();const button=event.submitter,result=document.getElementById(resultId),payload=Object.fromEntries(new FormData(form).entries());if(!payload.due_date)delete payload.due_date;if(!payload.amount_eur)delete payload.amount_eur;button.disabled=true;result.textContent='Saving…';try{const saved=await api(path,{method:'POST',body:JSON.stringify(payload)});form.reset();if(delivery){const now=new Date(Date.now()-new Date().getTimezoneOffset()*60000);form.elements.service_at.value=now.toISOString().slice(0,16)}result.textContent=saved.message||success;toast(saved.message||success);await loadWorkerPortal()}catch(error){result.textContent=error.message;toast(error.message)}finally{button.disabled=false}};
  }
  window.renderWorkerPortal=function(){if(originalRender)originalRender();renderContractorPortal()};
})();
