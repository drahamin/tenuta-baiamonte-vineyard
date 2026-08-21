(function treatmentDecisionTools(){
  const statusText=value=>String(value||'unknown').replaceAll('_',' ');
  const optionHtml=(rows,value)=>rows.map(row=>`<option value="${esc(row.code)}" ${row.code===value?'selected':''}>${esc(row.label)}</option>`).join('');
  const localDay=(offset=0)=>{const value=new Date();value.setDate(value.getDate()+offset);return value.toISOString().slice(0,10)};

  function targetsFor(crop){
    return (state.treatmentDashboard?.scenario_options?.targets||[]).filter(row=>row.crop_scope===crop);
  }

  function renderReviewInstructions(guidance){
    const node=$('treatmentFieldReviewInstructions');
    if(!node)return;
    const photos=guidance?.photos||[],measurements=guidance?.measurements||[];
    node.innerHTML=`<p><b>AI evidence required · at least ${Number(guidance?.minimum_photo_set||4)} useful photos</b></p><div class="review-columns"><div><span>Photos</span><ul>${photos.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div><div><span>Measurements</span><ul>${measurements.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div></div><p class="safety-note">${esc(guidance?.ai_accuracy_rule||'AI results remain limited to the sampled scope.')}</p>`;
  }

  function renderInventoryReadiness(board){
    const node=$('treatmentInventoryReadiness'),readiness=board.inventory_readiness||{};
    if(!node)return;
    node.className=`treatment-inventory-readiness ${esc(readiness.status||'review')}`;
    node.innerHTML=`<b>Inventory readiness · ${esc(statusText(readiness.status))}</b><span>${esc(readiness.message||'Inventory evidence requires review.')}</span>${readiness.needed_count?`<small>${Number(readiness.needed_count)} needed item${Number(readiness.needed_count)===1?'':'s'}</small>`:''}`;
  }

  function safetyMarkup(audit){
    if(!audit)return'';
    return `<section class="treatment-safety-audit ${esc(audit.status)}"><header><b>Safety evidence · ${esc(statusText(audit.status))}</b><span>${Number(audit.blocker_count||0)} open check${Number(audit.blocker_count||0)===1?'':'s'}</span></header>${(audit.checks||[]).map(check=>`<div class="safety-check ${esc(check.status)}"><i></i><span><b>${esc(check.label)}</b><small>${esc(check.detail)}</small></span><em>${esc(statusText(check.status))}</em></div>`).join('')}<p>${esc(audit.rule||'Unknown evidence is not reused for prediction.')}</p></section>`;
  }

  function decorateTreatmentSafety(board){
    const rows=board.treatments||[],complete=new Set(['completed','applied']),inactive=new Set(['cancelled','canceled','rejected','void']);
    const groups={
      treatmentPlannedList:rows.filter(row=>!complete.has(String(row.status||'').toLowerCase())&&!inactive.has(String(row.status||'').toLowerCase())),
      treatmentCompletedList:rows.filter(row=>complete.has(String(row.status||'').toLowerCase())),
      treatmentList:rows,
    };
    Object.entries(groups).forEach(([id,items])=>{
      const details=$(`${id}`)?.querySelectorAll('.treatment-row')||[];
      details.forEach((detail,index)=>{const body=detail.querySelector('.treatment-detail'),row=items[index];if(body&&row?.safety_audit)body.insertAdjacentHTML('beforeend',safetyMarkup(row.safety_audit))});
    });
    const summary=board.existing_treatment_safety_audit?.summary||{};
    const node=$('treatmentSummary');
    if(node)node.insertAdjacentHTML('beforeend',`<article class="metric ${Number(summary.blocked||0)?'alert-metric':''}"><span>Safety evidence</span><strong>${Number(summary.verified||0)} verified</strong><small>${Number(summary.attention||0)} attention · ${Number(summary.blocked||0)} PHI conflict</small></article>`);
  }

  function renderSimulatorResult(result){
    const node=$('treatmentSimulatorResult'),prediction=result.prediction||{},guidance=result.product_guidance||{},mix=guidance.mixture||{},components=mix.components||[],needed=guidance.needed_list||[],review=result.field_review_guidance||{},readiness=result.inventory_readiness||{};
    if(!node)return;
    node.hidden=false;
    node.innerHTML=`<div class="tool-result-head"><div><span>HYPOTHETICAL · NOT SAVED</span><h3>${esc(prediction.headline||'Scenario result')}</h3></div><strong>${esc(prediction.timing_label||'Review timing pending')}</strong></div><p>${esc(prediction.why||'')}</p><div class="simulation-result-grid"><article><span>Product decision</span><b>${esc(guidance.preferred_candidate?.product_name||'No verified candidate')}</b><small>${esc(guidance.message||'')}</small></article><article><span>Inventory</span><b>${esc(statusText(readiness.status))}</b><small>${esc(readiness.message||'')}</small></article><article><span>Field evidence</span><b>${Number(review.minimum_photo_set||4)} useful photos minimum</b><small>${esc(review.ai_accuracy_rule||'')}</small></article></div>${components.length?`<h4>Calculated primary mixture</h4>${components.map(item=>`<div class="simulation-product"><b>${esc(item.product_name)}</b><span>${item.total==null?'Total pending':`${fmt(item.total)} ${esc(item.total_unit)}`} · ${item.per_100_l==null?'tank rate pending':`${fmt(item.per_100_l)} ${esc(item.per_100_l_unit)}`} · PHI ${Number(item.phi_days||0)} days</span></div>`).join('')}`:''}${needed.length?`<h4>Needed stock</h4>${needed.map(item=>`<div class="simulation-product needs-stock"><b>${esc(item.product_name)}</b><span>${item.needed==null?'Count or reconcile first':`${fmt(item.needed)} ${esc(item.unit)} needed`} · ${fmt(item.on_hand)} on hand</span></div>`).join('')}`:''}${(mix.hard_blocks||[]).length?`<details open><summary>Cannot authorize until ${mix.hard_blocks.length} checks are resolved</summary><ul>${mix.hard_blocks.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></details>`:''}<p class="safety-note">${esc(result.guardrail||'Hypothetical decision support only.')}</p>`;
  }

  function renderTreatmentTools(){
    const board=state.treatmentDashboard||{};
    renderInventoryReadiness(board);
    decorateTreatmentSafety(board);
    const simulator=$('treatmentSimulatorForm'),reviewForm=$('treatmentFieldReviewForm');
    if(!simulator||!reviewForm)return;
    simulator.elements.crop_scope.value=board.crop_scope||state.treatmentCrop||'vineyard';
    if(!simulator.elements.scenario_date.value)simulator.elements.scenario_date.value=localDay();
    if(!simulator.elements.growth_stage.dataset.ready){simulator.elements.growth_stage.insertAdjacentHTML('beforeend',(state.reference?.phenology_stages||[]).map(row=>`<option value="${esc(row.code)}">${esc(row.label)}</option>`).join(''));simulator.elements.growth_stage.dataset.ready='1'}
    const refreshSimulatorTargets=()=>{const crop=simulator.elements.crop_scope.value,current=simulator.elements.target_code.value,targets=targetsFor(crop);simulator.elements.target_code.innerHTML=optionHtml(targets,targets.some(row=>row.code===current)?current:targets[0]?.code)};
    refreshSimulatorTargets();
    if(!simulator.dataset.bound){
      simulator.dataset.bound='1';
      simulator.elements.crop_scope.onchange=refreshSimulatorTargets;
      simulator.onsubmit=async event=>{event.preventDefault();const button=event.submitter,payload=Object.fromEntries(new FormData(simulator).entries());if(payload.area_ha==='')delete payload.area_ha;button.disabled=true;try{const result=await api('api/v1/treatments/simulate',{method:'POST',body:JSON.stringify(payload)});state.treatmentSimulation=result;renderSimulatorResult(result)}catch(error){toast(error.message)}finally{button.disabled=false}};
    }
    if(state.treatmentSimulation)renderSimulatorResult(state.treatmentSimulation);

    const currentTarget=board.prediction?.target_code||(board.latest_hail_followup?'hail_wound_followup':targetsFor(board.crop_scope||'vineyard')[0]?.code),reviewTargets=targetsFor(board.crop_scope||'vineyard');
    reviewForm.elements.target_code.innerHTML=optionHtml(reviewTargets,currentTarget);
    const blocks=state.blocks||state.reference?.blocks||[];
    reviewForm.elements.block_id.innerHTML='<option value="">Whole estate · representative survey</option>'+blocks.map(row=>`<option value="${esc(row.id)}">${esc(row.code||row.name)} · ${esc(row.name||'')}</option>`).join('');
    if(!reviewForm.elements.due_date.value)reviewForm.elements.due_date.value=localDay(board.latest_hail_followup?1:2);
    if(board.latest_hail_followup)reviewForm.elements.event_type.value='hail';
    renderReviewInstructions(board.field_review_guidance||{});
    if(!reviewForm.dataset.bound){
      reviewForm.dataset.bound='1';
      reviewForm.onchange=event=>{if(['target_code','event_type'].includes(event.target.name)){const target=reviewTargets.find(row=>row.code===reviewForm.elements.target_code.value),hail=reviewForm.elements.event_type.value==='hail'||target?.code==='hail_wound_followup';renderReviewInstructions({...board.field_review_guidance,target_code:target?.code,event_type:reviewForm.elements.event_type.value,minimum_photo_set:hail?6:4})}};
      reviewForm.onsubmit=async event=>{event.preventDefault();const button=event.submitter,payload=Object.fromEntries(new FormData(reviewForm).entries());payload.crop_scope=board.crop_scope||'vineyard';button.disabled=true;try{const result=await api('api/v1/treatments/field-review-requests',{method:'POST',body:JSON.stringify(payload)}),node=$('treatmentFieldReviewResult');node.hidden=false;node.innerHTML=`<b>${esc(result.title)}</b><span>Due ${esc(String(result.due_date).slice(0,10))} · task created in Work Plan</span>`;toast('Field review and photo instructions added to Work Plan')}catch(error){toast(error.message)}finally{button.disabled=false}};
    }
  }

  const baseRenderTreatments=renderTreatments;
  renderTreatments=function(){baseRenderTreatments();renderTreatmentTools()};
})();
