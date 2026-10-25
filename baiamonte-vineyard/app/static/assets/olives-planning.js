(function(){
  window.renderOliveHarvestPlan=function(oliveDashboard){
    const harvestPlan=oliveDashboard?.harvest_plan||{},capacity=oliveDashboard?.harvest_capacity_plan||{},planForm=$('oliveHarvestPlanForm');
    if(planForm){
      for(const name of ['window_start','window_end','crew_lead','crew_description','crew_size','crate_capacity_kg','planned_crop_kg','crew_capacity_crates_per_day','mill_status','notes']){
        if(planForm.elements[name])planForm.elements[name].value=harvestPlan[name]??(name==='crate_capacity_kg'?15:name==='mill_status'?'not_confirmed':'');
      }
      $('oliveHarvestPlanStatus').textContent=harvestPlan.window_start?'Saved owner plan':'Plan not saved';
    }
    if($('oliveCapacityBasis'))$('oliveCapacityBasis').textContent=`${capacity.source||'No crop basis'}${capacity.historical_years?.length?` · ${capacity.historical_years.join(', ')}`:''}`;
    if($('oliveCapacityMetrics'))$('oliveCapacityMetrics').innerHTML=`<span><small>EXPECTED CROP</small><b>${capacity.expected_olive_kg==null?'—':fmt(capacity.expected_olive_kg)+' kg'}</b><em>${capacity.low_olive_kg==null?'No historical range':`${fmt(capacity.low_olive_kg)}–${fmt(capacity.high_olive_kg)} kg historical scenario`}</em></span><span><small>${fmt(capacity.crate_capacity_kg||15)} KG CRATES</small><b>${capacity.expected_crates==null?'—':fmt(capacity.expected_crates)+' crates'}</b><em>${capacity.low_crates==null?'Crop estimate needed':`${fmt(capacity.low_crates)}–${fmt(capacity.high_crates)} crate scenario`}</em></span><span><small>EXPECTED OIL</small><b>${capacity.expected_oil_liters==null?'—':fmt(capacity.expected_oil_liters)+' L'}</b><em>${capacity.historical_oil_l_per_kg==null?'Conversion history needed':`${fmt(capacity.historical_oil_l_per_kg)} L/kg estate conversion`}</em></span><span><small>CREW</small><b>${esc(capacity.crew_description||capacity.crew_lead||'Not set')}</b><em>${capacity.crew_size?`${fmt(capacity.crew_size)} people`:'Headcount needed'}</em></span><span><small>MILL</small><b>${esc(String(capacity.mill_status||'not_confirmed').replaceAll('_',' '))}</b><em>Same-day milling should be fixed before picking</em></span><span><small>OPEN INPUTS</small><b>${capacity.pending_inputs?.length||0}</b><em>${esc((capacity.pending_inputs||[]).join(' · ')||'Operational plan complete')}</em></span>`;
    if($('oliveCapacityGuardrail'))$('oliveCapacityGuardrail').textContent=capacity.guardrail||'';
  };
  async function refreshOlivePlan(){state.olives=await api(`api/v1/olives/dashboard?year=${state.year}`);renderOlives()}
  async function saveOliveHarvestPreference(event){event.preventDefault();const form=event.currentTarget,button=event.submitter,payload=Object.fromEntries(new FormData(form).entries());button.disabled=true;try{await api(`api/v1/olives/harvest-preference/${state.year}`,{method:'PUT',body:JSON.stringify(payload)});await refreshOlivePlan();toast('Olive harvest strategy saved')}catch(error){toast(error.message)}finally{button.disabled=false}}
  async function saveOliveHarvestPlan(event){event.preventDefault();const form=event.currentTarget,button=event.submitter,payload=Object.fromEntries(new FormData(form).entries());button.disabled=true;try{await api(`api/v1/olives/harvest-plan/${state.year}`,{method:'PUT',body:JSON.stringify(payload)});await refreshOlivePlan();toast('Olive harvest plan saved and recalculated')}catch(error){toast(error.message)}finally{button.disabled=false}}
  if($('oliveHarvestPreferenceForm'))$('oliveHarvestPreferenceForm').onsubmit=saveOliveHarvestPreference;
  if($('oliveHarvestPlanForm'))$('oliveHarvestPlanForm').onsubmit=saveOliveHarvestPlan;
})();
