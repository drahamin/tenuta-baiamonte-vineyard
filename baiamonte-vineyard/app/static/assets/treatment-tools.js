(function treatmentDecisionTools(){
  const statusText=value=>String(value||'unknown').replaceAll('_',' ');
  const optionHtml=(rows,value)=>rows.map(row=>`<option value="${esc(row.code)}" ${row.code===value?'selected':''}>${esc(row.label)}</option>`).join('');
  const localDay=(offset=0)=>{const value=new Date();value.setDate(value.getDate()+offset);return value.toISOString().slice(0,10)};

  window.openProductLabelIntakeReview=function(item,data,id){const suggestions=Array.isArray(data.suggested_database_records)?data.suggested_database_records:[],fields=suggestions[0]?.fields||suggestions[0]?.values||{},uncertainties=Array.isArray(data.uncertainties)?data.uncertainties:[],value=(...keys)=>{for(const key of keys)if(fields[key]!=null)return fields[key];return''},suggestedName=String(value('product_name','name')||''),expected=suggestedName.toLowerCase(),products=(state.reference?.products||[]).filter(row=>['plant_protection','fertilizer'].includes(String(row.product_type||'')));$('intakeDialogTitle').textContent=item.title||item.original_filename||'Product information';$('intakeDetail').innerHTML=`<p>${esc(data.summary||item.ai_summary||'AI product analysis ready for review.')}</p>${uncertainties.length?`<article class="panel muted-panel"><h3>Conflicts or missing evidence</h3><p>${uncertainties.map(item=>esc(factText(item))).join('<br>')}</p></article>`:''}<form id="productEvidenceApprovalForm" class="completion-form"><p class="safety-note">Approval stores source-linked evidence. You may match an existing input or create a new reviewed catalog product; treatment authorization and prediction eligibility remain separate approvals.</p><label>Estate product<select name="product_id" required><option value="">Choose matching product</option><option value="__new__" ${products.some(row=>String(row.name||'').toLowerCase()===expected)?'':'selected'}>Create a new product from this source</option>${products.map(row=>`<option value="${esc(row.id)}" ${String(row.name||'').toLowerCase()===expected?'selected':''}>${esc(row.name)}</option>`).join('')}</select></label><div class="field-row new-product-fields"><label>New product name<input name="new_product_name" value="${esc(suggestedName)}" placeholder="Required only when creating"></label><label>Product type<select name="product_type"><option value="plant_protection">Plant protection</option><option value="fertilizer">Fertilizer / biostimulant</option></select></label><label>Inventory unit<input name="product_unit" value="${esc(value('unit','inventory_unit')||'L')}" placeholder="L, kg, ml, g"></label></div><div class="field-row"><label>Active ingredient<input name="active_ingredient" value="${esc(value('active_ingredient'))}"></label><label>Registration number<input name="registration_number" value="${esc(value('registration_number'))}"></label><label>Manufacturer / supplier<input name="supplier" value="${esc(value('manufacturer','supplier'))}"></label></div><label>Evidence type<select name="evidence_type"><option value="container_label">Container label</option><option value="manufacturer_label">Manufacturer label</option><option value="sds">Safety sheet / SDS</option><option value="technical_product_page">Technical sheet</option><option value="owner_document">Other owner document</option></select></label><div class="field-row"><label>Formulation<input name="formulation" value="${esc(value('formulation','observed_form'))}" placeholder="liquid, powder, WG…"></label><label>Lot<input name="lot_number" value="${esc(value('lot_number','lot'))}"></label></div><div class="field-row"><label>Minimum rate<input name="rate_min" type="number" min="0" step="0.001" value="${esc(value('rate_min','observed_rate'))}"></label><label>Maximum rate<input name="rate_max" type="number" min="0" step="0.001" value="${esc(value('rate_max'))}"></label><label>Rate unit<input name="rate_unit" value="${esc(value('rate_unit','observed_rate_unit'))}" placeholder="L/ha, ml/100 L…"></label></div><label>Reviewed evidence notes<textarea name="notes" rows="5">${esc([value('directions','notes'),...uncertainties.map(factText)].filter(Boolean).join('\n'))}</textarea></label><div class="form-actions"><a class="button secondary" href="api/v1/intake/${esc(id)}/file" target="_blank" rel="noopener">View source</a><button type="submit">Approve and add product evidence</button></div></form>`;$('intakeDialog').showModal();const form=$('productEvidenceApprovalForm'),syncNew=()=>{const creating=form.elements.product_id.value==='__new__';form.querySelectorAll('.new-product-fields input,.new-product-fields select').forEach(field=>field.disabled=!creating);form.elements.new_product_name.required=creating};form.elements.product_id.onchange=syncNew;syncNew();form.onsubmit=async event=>{event.preventDefault();const button=event.submitter,payload=Object.fromEntries(new FormData(form).entries());payload.create_product=payload.product_id==='__new__';button.disabled=true;try{const result=await api(`api/v1/treatments/product-evidence/intake/${encodeURIComponent(id)}/approve`,{method:'POST',body:JSON.stringify(payload)});$('intakeDialog').close();toast(`${result.product_name} ${result.created_product?'added with evidence':'evidence approved'}`);await loadAll()}catch(error){toast(error.message)}finally{button.disabled=false}}};

  function targetsFor(crop){
    return (state.treatmentDashboard?.scenario_options?.targets||[]).filter(row=>row.crop_scope===crop);
  }

  function renderReviewInstructions(guidance){
    const node=$('treatmentFieldReviewInstructions');
    if(!node)return;
    const photos=guidance?.photos||[],measurements=guidance?.measurements||[];
    node.innerHTML=`<p><b>Structured field observations are sufficient · photos optional</b></p><div class="review-columns"><div><span>Optional photo guidance · ${Number(guidance?.recommended_photo_set||4)} suggested</span><ul>${photos.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div><div><span>Measurements</span><ul>${measurements.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div></div><p class="safety-note">${esc(guidance?.ai_accuracy_rule||'AI results remain limited to the sampled scope.')}</p>`;
  }

  function renderInventoryReadiness(board){
    const node=$('treatmentInventoryReadiness'),readiness=board.inventory_readiness||{};
    if(!node)return;
    const issues=readiness.reconciliation?.issues||[];
    node.className=`treatment-inventory-readiness ${esc(readiness.status||'review')}`;
    node.innerHTML=`<b>Inventory readiness · ${esc(statusText(readiness.status))}</b><span>${esc(readiness.message||'Inventory evidence requires review.')}</span>${readiness.needed_count?`<small>${Number(readiness.needed_count)} needed item${Number(readiness.needed_count)===1?'':'s'}</small>`:''}${issues.length?`<details><summary>${issues.length} confirmed-use inventory exception${issues.length===1?'':'s'}</summary>${issues.map(item=>`<p><b>${esc(item.purpose||'Treatment')} · ${esc(item.product_name||'Product')}</b><small>${fmt(item.total_used)} ${esc(String(item.dose_unit||'').split('/')[0].trim())} recorded · stock unit ${esc(item.product_unit||'unknown')}<br>${esc(item.reason||'Inventory evidence requires review.')}</small></p>`).join('')}</details>`:''}`;
  }

  function renderRecordEvidenceGaps(board){
    const node=$('treatmentEvidenceGaps'),gaps=board.record_evidence_gaps||[];
    if(!node)return;
    node.hidden=!gaps.length;
    node.innerHTML=gaps.map(gap=>`<article><span>AUTHORITATIVE SOURCE REQUIRED</span><b>${esc(gap.title)}</b><p>${esc(gap.detail)}</p></article>`).join('');
  }

  function renderSprayerConfiguration(rows,defaults=state.sprayerDefaults||{}){
    const form=$('sprayerConfigForm');
    if(!form)return;
    const current=String(form.elements.equipment_id.value||'');
    form.elements.equipment_id.innerHTML='<option value="">Add another sprayer</option>'+rows.map(row=>`<option value="${esc(row.equipment_id)}" ${String(row.equipment_id)===current?'selected':''}>${esc(row.name)} · ${esc(statusText(row.calibration_status||'needs_measurement'))}</option>`).join('');
    const fill=row=>{const source=row||defaults;for(const name of ['name','make_model','tank_capacity_l','usable_capacity_l','calibration_status','calibrated_on','nozzle_setup','flow_l_min','operating_pressure_bar','travel_speed_kph','carrier_rate_l_ha','source_reference','notes'])if(form.elements[name])form.elements[name].value=source?.[name]??(name==='calibration_status'?'needs_measurement':'')};
    form.elements.equipment_id.onchange=()=>fill(rows.find(row=>String(row.equipment_id)===String(form.elements.equipment_id.value))||null);
    const preferred=rows.find(row=>String(row.name||'').toLowerCase()===String(defaults.name||'').toLowerCase())||rows[0];
    if(!current&&preferred){form.elements.equipment_id.value=preferred.equipment_id;fill(preferred)}else if(!current)fill(null);
  }

  async function loadSprayerConfiguration(){
    try{const [rows,defaults]=await Promise.all([api('api/v1/treatments/sprayers'),api('api/v1/treatments/sprayers/defaults')]);state.sprayerProfiles=rows;state.sprayerDefaults=defaults;renderSprayerConfiguration(rows||[],defaults||{})}catch(error){toast(error.message)}
  }

  function safetyMarkup(audit,row){
    if(!audit)return'';
    const mixture=(audit.checks||[]).find(check=>check.code==='mixture'),canReview=mixture&&['unverified','stale'].includes(mixture.status);
    return `<section class="treatment-safety-audit ${esc(audit.status)}"><header><b>Safety evidence · ${esc(statusText(audit.status))}</b><span>${Number(audit.blocker_count||0)} open check${Number(audit.blocker_count||0)===1?'':'s'}</span></header>${(audit.checks||[]).map(check=>`<div class="safety-check ${esc(check.status)}"><i></i><span><b>${esc(check.label)}</b><small>${esc(check.detail)}</small></span><em>${esc(statusText(check.status))}</em></div>`).join('')}${canReview?`<button type="button" class="small-button" data-mixture-review="${esc(row.id)}">Review exact mixture</button>`:''}<p>${esc(audit.rule||'Unknown evidence is not reused for prediction.')}</p></section>`;
  }

  function openMixtureReview(row){
    const dialog=$('recordDialog'),list=$('recordDialogList');
    if(!dialog||!list)return toast('Review window is unavailable');
    $('recordDialogTitle').textContent='Exact mixture review';
    list.className='list';
    list.innerHTML=`<form id="mixtureApprovalForm" class="completion-form"><div class="data-status"><b>${esc(row.purpose||'Completed treatment')}</b><span>${esc(row.products||row.source_products||'Structured product mixture')} · ${esc(String(row.application_date||'').slice(0,10))}</span></div><p class="safety-note">This approval is tied to the exact current products, rates and totals. Editing the recipe automatically makes the approval stale.</p><label>Decision<select name="status"><option value="verified">Verified compatible</option><option value="rejected">Rejected / keep separate</option></select></label><label>Jar test<select name="jar_test_status"><option value="passed">Passed</option><option value="not_required">Not required by current directions</option><option value="failed">Failed</option><option value="not_recorded">Not recorded</option></select></label><div class="check-grid"><label><input type="checkbox" name="current_labels_confirmed"> Current labels checked</label><label><input type="checkbox" name="exact_combination_confirmed"> Exact combination checked</label></div><label>Compatibility basis<textarea name="compatibility_basis" maxlength="4000" placeholder="Current label sections, manufacturer compatibility statement, or Agronomist basis"></textarea></label><label>Mixing sequence<textarea name="sequence_notes" maxlength="4000" placeholder="Order, agitation, water-quality conditions, separation requirements"></textarea></label><label>Review notes<textarea name="notes" maxlength="4000" placeholder="Jar-test result, rejection reason, limitations or follow-up"></textarea></label><div class="form-actions"><button type="button" data-close-mixture>Cancel</button><button type="submit">Save mixture review</button></div></form>`;
    dialog.showModal();
    list.querySelector('[data-close-mixture]').onclick=()=>dialog.close();
    list.querySelector('#mixtureApprovalForm').onsubmit=async event=>{event.preventDefault();const button=event.submitter,form=new FormData(event.currentTarget),payload=Object.fromEntries(form.entries());payload.current_labels_confirmed=form.has('current_labels_confirmed');payload.exact_combination_confirmed=form.has('exact_combination_confirmed');button.disabled=true;try{await api(`api/v1/treatments/${encodeURIComponent(row.id)}/mixture-approval`,{method:'POST',body:JSON.stringify(payload)});dialog.close();toast('Exact mixture review saved');await loadAll()}catch(error){toast(error.message)}finally{button.disabled=false}};
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
      details.forEach((detail,index)=>{const body=detail.querySelector('.treatment-detail'),row=items[index];if(body&&row?.safety_audit)body.insertAdjacentHTML('beforeend',safetyMarkup(row.safety_audit,row))});
    });
    document.querySelectorAll('[data-mixture-review]').forEach(button=>{button.onclick=()=>{const row=rows.find(item=>String(item.id)===String(button.dataset.mixtureReview));if(row)openMixtureReview(row)}});
    const summary=board.existing_treatment_safety_audit?.summary||{};
    const node=$('treatmentSummary');
    if(node)node.insertAdjacentHTML('beforeend',`<article class="metric ${Number(summary.blocked||0)?'alert-metric':''}"><span>Safety evidence</span><strong>${Number(summary.verified||0)} verified</strong><small>${Number(summary.attention||0)} attention · ${Number(summary.blocked||0)} PHI conflict</small></article>`);
  }

  function renderSimulatorResult(result){
    const node=$('treatmentSimulatorResult'),prediction=result.prediction||{},guidance=result.product_guidance||{},mix=guidance.mixture||{},components=mix.components||[],needed=guidance.needed_list||[],review=result.field_review_guidance||{},readiness=result.inventory_readiness||{};
    if(!node)return;
    node.hidden=false;
    node.innerHTML=`<div class="tool-result-head"><div><span>HYPOTHETICAL · NOT SAVED</span><h3>${esc(prediction.headline||'Scenario result')}</h3></div><strong>${esc(prediction.timing_label||'Review timing pending')}</strong></div><p>${esc(prediction.why||'')}</p><div class="simulation-result-grid"><article><span>Product decision</span><b>${esc(guidance.preferred_candidate?.product_name||'No verified candidate')}</b><small>${esc(guidance.message||'No current catalog product has a verified label for this crop and target. Add and review a matching label or SDS; the simulator will not invent an authorization.')}</small></article><article><span>Inventory</span><b>${esc(statusText(readiness.status))}</b><small>${esc(readiness.message||'')}</small></article><article><span>Field evidence</span><b>Photos optional</b><small>${esc(review.ai_accuracy_rule||'Structured observations and counts can be submitted without photos.')}</small></article></div>${components.length?`<h4>Calculated primary mixture</h4>${components.map(item=>`<div class="simulation-product"><b>${esc(item.product_name)}</b><span>${item.total==null?'Total pending':`${fmt(item.total)} ${esc(item.total_unit)}`} · ${item.per_100_l==null?'tank rate pending':`${fmt(item.per_100_l)} ${esc(item.per_100_l_unit)}`} · PHI ${Number(item.phi_days||0)} days</span></div>`).join('')}`:''}${needed.length?`<h4>Needed stock</h4>${needed.map(item=>`<div class="simulation-product needs-stock"><b>${esc(item.product_name)}</b><span>${item.needed==null?'Reconcile unknown use first':`${fmt(item.needed)} ${esc(item.unit)} needed`} · ${fmt(item.on_hand)} ledger balance${Number(item.on_hand)<0?' · purchase receipt pending':''}</span></div>`).join('')}`:''}${(mix.hard_blocks||[]).length?`<details open><summary>Cannot authorize until ${mix.hard_blocks.length} checks are resolved</summary><ul>${mix.hard_blocks.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></details>`:''}<p class="safety-note">${esc(result.guardrail||'Hypothetical decision support only.')}</p>`;
  }

  function renderTreatmentTools(){
    const board=state.treatmentDashboard||{};
    renderInventoryReadiness(board);
    renderRecordEvidenceGaps(board);
    decorateTreatmentSafety(board);
    const simulator=$('treatmentSimulatorForm'),reviewForm=$('treatmentFieldReviewForm'),labelForm=$('productLabelIntakeForm'),sprayerForm=$('sprayerConfigForm');
    if(!simulator||!reviewForm)return;
    if(labelForm){
      const selected=labelForm.elements.product_name.value,treatmentProducts=(state.reference?.products||[]).filter(row=>['plant_protection','fertilizer'].includes(String(row.product_type||'')));
      labelForm.elements.product_name.innerHTML='<option value="">Let AI identify it</option>'+treatmentProducts.map(row=>`<option value="${esc(row.name)}" ${row.name===selected?'selected':''}>${esc(row.name)}</option>`).join('');
      if(!labelForm.dataset.bound){
        labelForm.dataset.bound='1';
        labelForm.onsubmit=async event=>{event.preventDefault();const button=event.submitter,data=new FormData(labelForm),product=String(data.get('product_name')||'').trim(),kind=String(data.get('evidence_type')||'product document').replaceAll('_',' '),context=String(data.get('context')||'').trim();data.delete('product_name');data.delete('evidence_type');data.delete('context');data.set('title',`${product||'Unidentified product'} · ${kind}`);data.set('notes',`PRODUCT EVIDENCE INTAKE. Expected product: ${product||'identify from source'}. Evidence type: ${kind}. ${context}`.trim());button.disabled=true;try{const response=await fetch('api/v1/intake/upload',{method:'POST',body:data}),result=await response.json().catch(()=>({}));if(!response.ok)throw new Error(result.detail||'Upload failed');const node=$('productLabelIntakeResult');node.hidden=false;node.innerHTML='<b>Uploaded for AI analysis</b><span>The source is preserved and will appear in Incoming information for human review.</span>';labelForm.reset();toast('Product information uploaded for review');await loadAll()}catch(error){toast(error.message)}finally{button.disabled=false}};
      }
    }
    if(sprayerForm&&!sprayerForm.dataset.bound){
      sprayerForm.dataset.bound='1';
      const panel=sprayerForm.closest('details');
      panel?.addEventListener('toggle',()=>{if(panel.open)loadSprayerConfiguration()});
      sprayerForm.onsubmit=async event=>{event.preventDefault();const button=event.submitter,payload=Object.fromEntries(new FormData(sprayerForm).entries());for(const key of ['tank_capacity_l','usable_capacity_l','flow_l_min','operating_pressure_bar','travel_speed_kph','carrier_rate_l_ha'])if(payload[key]!=='')payload[key]=Number(payload[key]);else payload[key]=null;button.disabled=true;try{const result=await api('api/v1/treatments/sprayers',{method:'POST',body:JSON.stringify(payload)}),node=$('sprayerConfigResult');node.hidden=false;node.innerHTML=`<b>Sprayer saved · ${esc(statusText(result.calibration_status))}</b><span>Treatment calculations will use this profile after refresh.</span>`;toast('Sprayer configuration saved');await loadSprayerConfiguration();await loadTreatmentProgram(state.treatmentCrop||'vineyard')}catch(error){toast(error.message)}finally{button.disabled=false}};
    }
    simulator.elements.crop_scope.value=board.crop_scope||state.treatmentCrop||'vineyard';
    if(!simulator.elements.scenario_date.value)simulator.elements.scenario_date.value=localDay();
    {const stages=state.reference?.phenology_stages||[],current=simulator.elements.growth_stage.value;if(stages.length&&simulator.elements.growth_stage.options.length!==stages.length+1){simulator.elements.growth_stage.innerHTML='<option value="">Not supplied</option>'+stages.map(row=>`<option value="${esc(row.code)}">${esc(row.label)}</option>`).join('');if(stages.some(row=>row.code===current))simulator.elements.growth_stage.value=current}}
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
      reviewForm.onchange=event=>{if(['target_code','event_type'].includes(event.target.name)){const target=reviewTargets.find(row=>row.code===reviewForm.elements.target_code.value),hail=reviewForm.elements.event_type.value==='hail'||target?.code==='hail_wound_followup';renderReviewInstructions({...board.field_review_guidance,target_code:target?.code,event_type:reviewForm.elements.event_type.value,minimum_photo_set:0,recommended_photo_set:hail?6:4,photos_optional:true})}};
      reviewForm.onsubmit=async event=>{event.preventDefault();const button=event.submitter,payload=Object.fromEntries(new FormData(reviewForm).entries());payload.crop_scope=board.crop_scope||'vineyard';button.disabled=true;try{const result=await api('api/v1/treatments/field-review-requests',{method:'POST',body:JSON.stringify(payload)}),node=$('treatmentFieldReviewResult');node.hidden=false;node.innerHTML=`<b>${esc(result.title)}</b><span>Due ${esc(String(result.due_date).slice(0,10))} · task created in Work Plan · photos optional</span>`;toast('Field review added to Work Plan')}catch(error){toast(error.message)}finally{button.disabled=false}};
    }
  }

  const baseRenderTreatments=renderTreatments;
  renderTreatments=function(){baseRenderTreatments();renderTreatmentTools()};
})();
