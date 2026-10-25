(function () {
  const e = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character]));
  let loadedYear = null;
  let loading = null;
  let dashboard = null;
  let lastPayload = null;
  let simulationSequence = 0;
  let liveTimer = null;

  function stream(name) {
    const key = String(name).toLowerCase();
    return (dashboard?.streams || []).find(row => String(row.variety_name || '').toLowerCase().includes(key)) || {};
  }

  function numeric(form, name) {
    return Math.max(0, Number(form.elements[name]?.value || 0));
  }

  function calculateAllocation(form) {
    const designation = form.elements.designation_code.value;
    const nerello = numeric(form, 'estate_nerello_kg');
    const estateGrenache = numeric(form, 'estate_grenache_kg');
    const purchasedGrenache = numeric(form, 'purchased_grenache_kg');
    const grenachePct = numeric(form, 'blend_grenache_pct');
    const estatePct = numeric(form, 'blend_estate_grenache_pct');
    const allocateGrenache = nerello > 0 && estateGrenache + purchasedGrenache > 0;
    const nerelloYield = Number(stream('nerello mascalese').predictive_l_per_kg || .67);
    const grenacheYield = Number(stream('grenache').predictive_l_per_kg || .67);
    const blendGrenache = allocateGrenache && grenachePct < 100 ? nerello * nerelloYield * grenachePct / ((100 - grenachePct) * grenacheYield) : 0;
    const estateBlendGrenache = blendGrenache * estatePct / 100;
    const purchasedBlendGrenache = blendGrenache - estateBlendGrenache;
    return {
      designation, nerello, estateGrenache, purchasedGrenache, grenachePct, estatePct,
      allocateGrenache, nerelloYield, grenacheYield, blendGrenache,
      estateBlendGrenache, purchasedBlendGrenache,
      remainingEstateGrenache: Math.max(0, estateGrenache - estateBlendGrenache),
      remainingPurchasedGrenache: Math.max(0, purchasedGrenache - purchasedBlendGrenache),
    };
  }

  function renderLiveAllocation(form) {
    const node = document.getElementById('designationLiveAllocation');
    if (!node) return;
    const a = calculateAllocation(form);
    if (!a.allocateGrenache) {
      node.innerHTML = a.nerello && (a.estateGrenache + a.purchasedGrenache)
        ? '<b>Alicante / Grenache allocation needs both Nerello and available fruit.</b>'
        : '<b>No Grenache blend allocation</b><span>Select the Nerello + Grenache preset, or choose Terre Siciliane IGT / Vino and enter available fruit.</span>';
      node.classList.add('warning');
      return;
    }
    const fmt = value => Number(value || 0).toLocaleString(undefined, {maximumFractionDigits:3});
    const primaryL = a.nerello * a.nerelloYield + a.blendGrenache * a.grenacheYield;
    const shortage = [];
    if (a.estateBlendGrenache > a.estateGrenache + .001) shortage.push(`${fmt(a.estateBlendGrenache - a.estateGrenache)} kg estate Grenache short`);
    if (a.purchasedBlendGrenache > a.purchasedGrenache + .001) shortage.push(`${fmt(a.purchasedBlendGrenache - a.purchasedGrenache)} kg purchased Grenache short`);
    const etnaWarning = a.designation === 'etna_doc_rosso' ? 'Alicante is Grenache, but the current official Etna Rosso specification does not list this red variety; this what-if cannot be locked as compliant without written authority.' : '';
    node.classList.toggle('warning', Boolean(shortage.length || etnaWarning));
    node.innerHTML = `<div><small>CALCULATED NERELLO BLEND · ${fmt(a.grenachePct)}% BY PREDICTED WINE VOLUME</small><strong>${fmt(a.blendGrenache)} kg Alicante / Grenache</strong><span>${fmt(a.estateBlendGrenache)} kg estate · ${fmt(a.purchasedBlendGrenache)} kg purchased</span></div>
      <div><small>REMAINING AS SEPARATE ALICANTE / GRENACHE</small><strong>${fmt(a.remainingEstateGrenache + a.remainingPurchasedGrenache)} kg</strong><span>${fmt(a.remainingEstateGrenache)} kg estate · ${fmt(a.remainingPurchasedGrenache)} kg purchased</span></div>
      <div><small>PREDICTED FINAL NERELLO WINE</small><strong>${fmt(primaryL)} L · ${Math.floor(primaryL / .75).toLocaleString()} bottles</strong><span>${e(shortage.length ? shortage.join(' · ') : etnaWarning || 'Allocation fits the available source quantities')}</span></div>`;
  }

  function buildPayload(form) {
    const documented = Boolean(form.elements.purchase_eligibility_documented.checked);
    const a = calculateAllocation(form);
    const components = [
      ['Nerello Mascalese', 'estate', a.nerello, true, 'final_wine'],
      ['Grenache', 'estate', a.allocateGrenache ? a.estateBlendGrenache : a.estateGrenache, true, 'final_wine'],
      ['Grenache', 'purchased', a.allocateGrenache ? a.purchasedBlendGrenache : a.purchasedGrenache, documented, 'final_wine'],
      ['Grenache', 'estate', a.allocateGrenache ? a.remainingEstateGrenache : 0, true, 'grenache_single'],
      ['Grenache', 'purchased', a.allocateGrenache ? a.remainingPurchasedGrenache : 0, documented, 'grenache_single'],
      ['Nerello Cappuccio', 'planned_purchase', numeric(form, 'purchased_cappuccio_kg'), documented, 'final_wine'],
      ['Grecanico', 'estate', numeric(form, 'estate_grecanico_kg'), true, 'final_wine'],
    ].filter(row => row[2] > 0).map(row => ({variety_name: row[0], source_type: row[1], kg: Math.round(row[2] * 1000) / 1000, eligibility_documented: row[3], allocation: row[4]}));
    return {
      wine_name: form.elements.wine_name.value.trim(),
      designation_code: a.designation,
      wine_lot_id: form.elements.wine_lot_id.value || null,
      notes: form.elements.notes.value.trim(),
      secondary_wine_name: form.elements.secondary_wine_name.value.trim(),
      secondary_designation_code: form.elements.secondary_designation_code.value,
      blend_parameters: a.allocateGrenache ? {grenache_pct: a.grenachePct, estate_grenache_pct: a.estatePct} : null,
      components,
    };
  }

  function setNumber(form, name, value) {
    form.elements[name].value = Number(value || 0).toFixed(3).replace(/\.?0+$/, '');
  }

  function applyPreset(kind) {
    const form = document.getElementById('designationPlannerForm');
    if (!form || !dashboard) return;
    ['estate_nerello_kg','estate_grenache_kg','purchased_grenache_kg','purchased_cappuccio_kg','estate_grecanico_kg'].forEach(name => setNumber(form, name, 0));
    const nerello = stream('nerello mascalese');
    const grenache = stream('grenache');
    const grecanico = stream('grecanico');
    form.elements.purchase_eligibility_documented.checked = false;
    setNumber(form, 'blend_grenache_pct', 10);
    setNumber(form, 'blend_estate_grenache_pct', 70);
    form.elements.secondary_designation_code.value = 'terre_siciliane_igt';
    form.elements.secondary_wine_name.value = `Baiamonte ${state.year} Grenache single wine`;
    if (kind === 'blend') {
      form.elements.designation_code.value = 'terre_siciliane_igt';
      form.elements.wine_name.value = `Baiamonte ${state.year} Nerello + Grenache`;
      setNumber(form, 'estate_nerello_kg', nerello.estate_fruit_kg);
      setNumber(form, 'estate_grenache_kg', grenache.estate_fruit_kg);
      setNumber(form, 'purchased_grenache_kg', grenache.purchased_fruit_kg);
      form.elements.notes.value = 'Final red blend uses the selected Grenache percentage and source split. All remaining Grenache stays as a separate single wine.';
    } else if (kind === 'etna') {
      form.elements.designation_code.value = 'etna_doc_rosso';
      form.elements.wine_name.value = `Baiamonte ${state.year} Etna DOC Rosso candidate`;
      setNumber(form, 'estate_nerello_kg', nerello.estate_fruit_kg);
      setNumber(form, 'purchased_cappuccio_kg', 1);
      form.elements.notes.value = 'Candidate uses 1 kg planned purchased Nerello Cappuccio. Origin and eligibility evidence must be attached before legal verification.';
    } else {
      form.elements.designation_code.value = kind === 'superiore' ? 'sicilia_doc_grecanico_superiore' : 'sicilia_doc_grecanico';
      form.elements.wine_name.value = `Baiamonte ${state.year} Grecanico`;
      setNumber(form, 'estate_grecanico_kg', grecanico.estate_fruit_kg);
      form.elements.notes.value = kind === 'backoff'
        ? 'Backed off Grecanico Superiore to ordinary Sicilia DOC Grecanico. No laboratory report required for this lower internal designation decision.'
        : kind === 'superiore' ? 'Grecanico Superiore candidate; supporting designation evidence remains review-required.' : 'Ordinary Grecanico designation plan.';
    }
    renderLiveAllocation(form);
    simulate(form);
  }

  function renderSimulation(result) {
    const node = document.getElementById('designationSimulation');
    if (!node) return;
    node.classList.remove('empty');
    const messages = [...(result.errors || []).map(text => `<li class="designation-error">${e(text)}</li>`), ...(result.warnings || []).map(text => `<li>${e(text)}</li>`)];
    const primaryComponents = (result.components || []).filter(row => row.allocation === 'final_wine');
    const split = result.blend_parameters?.grenache_pct == null ? '' : `<p class="designation-allocation-note"><b>${Number(result.blend_parameters.grenache_pct).toLocaleString()}% Grenache by predicted wine volume</b> · ${Number(result.blend_parameters.estate_grenache_pct).toLocaleString()}% estate / ${Number(result.blend_parameters.purchased_grenache_pct).toLocaleString()}% purchased Grenache</p>`;
    const secondary = (result.secondary_products || []).map(product => `<article class="designation-output secondary"><header><div><small>SEPARATE WINE · ${e(product.designation_label)}</small><h4>${e(product.wine_name)}</h4></div><strong>${Number(product.predicted_bottles_750ml).toLocaleString()} bottles</strong></header><p>${Number(product.grapes_kg).toLocaleString()} kg Grenache → ${Number(product.predicted_wine_l).toLocaleString()} L</p><div class="designation-components">${(product.components || []).map(row => `<span><b>${e(row.source_type.replaceAll('_',' '))}</b> ${Number(row.kg).toLocaleString()} kg</span>`).join('')}</div><small>Reserved outside the Nerello blend · legal review required</small></article>`).join('');
    const legal = result.legal_production_scenarios || [];
    const legalComparison = `<div class="designation-legal-comparison"><header><div><small>DOCUMENTARY LEGAL PRODUCTION AMOUNT</small><b>${e(result.designation_label)}</b></div><span>${legal.length ? `${legal.length} matching scenario${legal.length === 1 ? '' : 's'}` : 'No matching ceiling recorded'}</span></header>${legal.length ? legal.map(row => {const difference=Number(row.wine_l||0)-Number(result.predicted_wine_l||0);return `<article><div><b>${e(row.scenario_label)}</b><small>${e(String(row.eligibility_status||'').replaceAll('_',' '))}</small></div><strong>${Number(row.grapes_kg||0).toLocaleString()} kg → ${Number(row.wine_l||0).toLocaleString()} L<br>${Number(row.full_bottles_750ml||0).toLocaleString()} bottles</strong><span class="${difference < 0 ? 'designation-stop' : 'designation-pass'}">Plan is ${Math.abs(difference).toLocaleString()} L ${difference < 0 ? 'over' : 'under'} this scenario</span><small>${e(row.caveat||'')}</small></article>`}).join('') : '<p>No documentary production ceiling matches this designation. This is not a zero allowance; legal review must supply or confirm the applicable amount.</p>'}<small>Scenarios are alternatives, not additive, and do not establish live SIAN entitlement.</small></div>`;
    node.innerHTML = `<div class="designation-result-head"><div><small>FINAL NERELLO WINE · ${e(result.designation_label)}</small><h4>${e(result.wine_name)}</h4></div><strong class="${result.can_lock ? 'designation-pass' : 'designation-stop'}">${result.can_lock ? 'Allocation can be locked' : 'Resolve before locking'}</strong></div>
      <div class="metric-grid compact-metrics"><article class="metric"><span>Grapes</span><strong>${Number(result.total_grapes_kg).toLocaleString()} kg</strong></article><article class="metric"><span>Predicted wine</span><strong>${Number(result.predicted_wine_l).toLocaleString()} L</strong></article><article class="metric"><span>750 ml bottles</span><strong>${Number(result.predicted_bottles_750ml).toLocaleString()}</strong></article><article class="metric"><span>Legal status</span><strong>Review required</strong></article></div>
      ${split}<div class="designation-components">${primaryComponents.map(row => `<span><b>${e(row.variety_name)}</b> ${Number(row.kg).toLocaleString()} kg · ${Number(row.share_pct).toLocaleString()}% · ${e(row.source_type.replaceAll('_',' '))}</span>`).join('')}</div>
      ${secondary ? `<div class="designation-output-grid">${secondary}</div>` : ''}
      ${legalComparison}
      ${messages.length ? `<ul class="designation-messages">${messages.join('')}</ul>` : ''}<p class="safety-note">${e(result.decision_note)}${result.official_source ? ` · <a href="${e(result.official_source)}" target="_blank" rel="noopener">Official production specification</a>` : ''}</p>`;
  }

  async function simulate(form) {
    const sequence = ++simulationSequence;
    lastPayload = buildPayload(form);
    const status = document.getElementById('designationPlannerStatus');
    if (status) status.textContent = 'Calculating…';
    try {
      const result = await api(`api/v1/vintage/designation-simulate?year=${state.year}`, {method:'POST', body:JSON.stringify(lastPayload)});
      if (sequence !== simulationSequence) return null;
      renderSimulation(result);
      if (status) status.textContent = result.can_lock ? 'Ready to lock' : 'Needs changes';
      return result;
    } catch (error) {
      if (status) status.textContent = 'Cannot simulate';
      toast(error.message);
      return null;
    }
  }

  function renderPlans() {
    const node = document.getElementById('designationPlans');
    if (!node) return;
    const plans = dashboard?.plans || [];
    node.classList.toggle('empty', !plans.length);
    node.innerHTML = plans.length ? plans.map(plan => {const secondary=plan.simulation?.secondary_products?.[0];return `<div class="list-row designation-plan-row"><span class="list-icon">§</span><div><b>${e(plan.wine_name)}</b><small>${e(plan.designation_label)} · ${e(plan.decision_status)} · legal ${e(String(plan.legal_review_status).replaceAll('_',' '))}</small><small>${Number(plan.projected_grapes_kg || 0).toLocaleString()} kg → ${Number(plan.projected_wine_l || 0).toLocaleString()} L → ${Number(plan.projected_bottles_750ml || 0).toLocaleString()} bottles${secondary?` · balance: ${Number(secondary.grapes_kg).toLocaleString()} kg separate Grenache`:''}</small></div></div>`}).join('') : 'No saved designation decisions.';
  }

  function renderReconciliation() {
    const node = document.getElementById('designationReconciliation');
    if (!node) return;
    const draft = dashboard?.reconciliation_draft;
    node.classList.toggle('empty', !draft);
    if (!draft) { node.textContent = 'No reconciliation sheet is attached to this vintage.'; return; }
    const total = (draft.working_actuals || []).reduce((sum,row) => sum + Number(row.volume_l || 0), 0);
    node.innerHTML = `<details class="designation-reconciliation-compact"><summary><b>${Number(total).toLocaleString()} L measured notes</b><span>Review only · expand evidence</span></summary><p class="safety-note">${e(draft.reporting_rule)}</p><div class="designation-reconciliation-values">${(draft.working_actuals || []).map(row => `<span><b>${e(row.lot)}</b> ${Number(row.volume_l).toLocaleString()} L<small>${e(row.note)}</small></span>`).join('')}</div><details><summary>Calculations written on the sheet</summary>${(draft.source_calculations || []).map(row => `<p><b>${e(row.wine)}:</b> ${e(row.calculation)} <small>· ${e(row.confidence.replaceAll('_',' '))}</small></p>`).join('')}</details></details>`;
  }

  function draw() {
    const form = document.getElementById('designationPlannerForm');
    if (!form || !dashboard) return;
    document.getElementById('designationGuardrail').textContent = dashboard.guardrail;
    const selected = form.elements.wine_lot_id.value;
    form.elements.wine_lot_id.innerHTML = `<option value="">No batch yet</option>${(state.grapes?.cellar_lots || []).map(row => `<option value="${e(row.id)}">${e(row.code)} — ${e(row.name)}</option>`).join('')}`;
    form.elements.wine_lot_id.value = selected;
    if (!form.dataset.bound) {
      form.dataset.bound = '1';
      form.elements.wine_name.value = `Baiamonte ${state.year} final wine`;
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const action = event.submitter?.dataset.designationAction || 'simulate';
        const result = await simulate(form);
        if (action !== 'lock' || !result?.can_lock) return;
        const payload = {...lastPayload, decision_status:'locked'};
        try {
          await api(`api/v1/vintage/designation-plans?year=${state.year}`, {method:'POST', body:JSON.stringify(payload)});
          toast('Production designation decision locked; legal review remains required');
          loadedYear = null;
          await loadDashboard();
          await loadAll();
        } catch (error) { toast(error.message); }
      });
      document.querySelectorAll('[data-designation-preset]').forEach(button => button.addEventListener('click', () => applyPreset(button.dataset.designationPreset)));
      const liveFields = new Set(['designation_code','estate_nerello_kg','estate_grenache_kg','purchased_grenache_kg','blend_grenache_pct','blend_estate_grenache_pct','purchased_cappuccio_kg','estate_grecanico_kg','secondary_designation_code']);
      const liveChange = event => {
        if (!liveFields.has(event.target?.name)) return;
        renderLiveAllocation(form);
        clearTimeout(liveTimer);
        liveTimer = setTimeout(() => simulate(form), 250);
      };
      form.addEventListener('input', liveChange);
      form.addEventListener('change', liveChange);
    }
    renderLiveAllocation(form);
    renderPlans();
    renderReconciliation();
    const status = document.getElementById('designationPlannerStatus');
    if (status && !lastPayload) status.textContent = `${(dashboard.plans || []).length} saved`;
  }

  async function loadDashboard() {
    if (loadedYear === state.year && dashboard) { draw(); return; }
    if (loading) return loading;
    loading = api(`api/v1/vintage/designation-plans?year=${state.year}`).then(value => {
      dashboard = value; loadedYear = state.year; draw();
    }).catch(error => {
      const status = document.getElementById('designationPlannerStatus');
      if (status) status.textContent = 'Unavailable';
      console.warn('Designation planner unavailable', error);
    }).finally(() => { loading = null; });
    return loading;
  }

  const previousRenderGrapes = renderGrapes;
  renderGrapes = function () { const value = previousRenderGrapes(); loadDashboard(); return value; };

  if (typeof fields !== 'undefined' && fields.cellar_lot) {
    const baseCellarLotFields = fields.cellar_lot;
    fields.cellar_lot = () => baseCellarLotFields().replace('<details><summary>More details</summary>', `<div class="field-row"><div class="field"><label>Designation plan</label><select name="designation_intent"><option value="">Not selected</option><option value="terre_siciliane_igt">Terre Siciliane IGT</option><option value="etna_doc_rosso">Etna DOC Rosso</option><option value="sicilia_doc_grecanico">Sicilia DOC Grecanico</option><option value="sicilia_doc_grecanico_superiore">Sicilia DOC Grecanico Superiore</option><option value="vino">Vino</option></select><small>Selection records intent; legal review is still required.</small></div><div class="field"><label>Blend components</label><input name="blend_components_text" placeholder="Nerello 80%; other component 20%"></div></div><div class="field"><label>Designation source note</label><input name="designation_source_note" placeholder="Eligibility document, enologist instruction, or decision reason"></div><details><summary>More details</summary>`);
  }
}());
