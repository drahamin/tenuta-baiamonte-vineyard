(function () {
  const e = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character]));
  let loadedYear = null;
  let loading = null;
  let dashboard = null;
  let lastPayload = null;

  function stream(name) {
    const key = String(name).toLowerCase();
    return (dashboard?.streams || []).find(row => String(row.variety_name || '').toLowerCase().includes(key)) || {};
  }

  function numeric(form, name) {
    return Math.max(0, Number(form.elements[name]?.value || 0));
  }

  function buildPayload(form) {
    const documented = Boolean(form.elements.purchase_eligibility_documented.checked);
    const components = [
      ['Nerello Mascalese', 'estate', numeric(form, 'estate_nerello_kg'), true],
      ['Grenache', 'estate', numeric(form, 'estate_grenache_kg'), true],
      ['Grenache', 'purchased', numeric(form, 'purchased_grenache_kg'), documented],
      ['Nerello Cappuccio', 'planned_purchase', numeric(form, 'purchased_cappuccio_kg'), documented],
      ['Grecanico', 'estate', numeric(form, 'estate_grecanico_kg'), true],
    ].filter(row => row[2] > 0).map(row => ({variety_name: row[0], source_type: row[1], kg: row[2], eligibility_documented: row[3]}));
    return {
      wine_name: form.elements.wine_name.value.trim(),
      designation_code: form.elements.designation_code.value,
      wine_lot_id: form.elements.wine_lot_id.value || null,
      notes: form.elements.notes.value.trim(),
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
    if (kind === 'blend') {
      form.elements.designation_code.value = 'terre_siciliane_igt';
      form.elements.wine_name.value = `Baiamonte ${state.year} Nerello + Grenache`;
      setNumber(form, 'estate_nerello_kg', nerello.estate_fruit_kg);
      setNumber(form, 'estate_grenache_kg', grenache.estate_fruit_kg);
      setNumber(form, 'purchased_grenache_kg', grenache.purchased_fruit_kg);
      form.elements.notes.value = 'Final red blend. Keep separate from the Etna DOC scenario.';
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
    simulate(form);
  }

  function renderSimulation(result) {
    const node = document.getElementById('designationSimulation');
    if (!node) return;
    node.classList.remove('empty');
    const messages = [...(result.errors || []).map(text => `<li class="designation-error">${e(text)}</li>`), ...(result.warnings || []).map(text => `<li>${e(text)}</li>`)];
    node.innerHTML = `<div class="designation-result-head"><div><small>${e(result.designation_label)}</small><h4>${e(result.wine_name)}</h4></div><strong class="${result.can_lock ? 'designation-pass' : 'designation-stop'}">${result.can_lock ? 'Composition can be locked' : 'Resolve before locking'}</strong></div>
      <div class="metric-grid compact-metrics"><article class="metric"><span>Grapes</span><strong>${Number(result.total_grapes_kg).toLocaleString()} kg</strong></article><article class="metric"><span>Predicted wine</span><strong>${Number(result.predicted_wine_l).toLocaleString()} L</strong></article><article class="metric"><span>750 ml bottles</span><strong>${Number(result.predicted_bottles_750ml).toLocaleString()}</strong></article><article class="metric"><span>Legal status</span><strong>Review required</strong></article></div>
      <div class="designation-components">${(result.components || []).map(row => `<span><b>${e(row.variety_name)}</b> ${Number(row.kg).toLocaleString()} kg · ${Number(row.share_pct).toLocaleString()}% · ${e(row.source_type.replaceAll('_',' '))}</span>`).join('')}</div>
      ${messages.length ? `<ul class="designation-messages">${messages.join('')}</ul>` : ''}<p class="safety-note">${e(result.decision_note)}${result.official_source ? ` · <a href="${e(result.official_source)}" target="_blank" rel="noopener">Official production specification</a>` : ''}</p>`;
  }

  async function simulate(form) {
    lastPayload = buildPayload(form);
    const status = document.getElementById('designationPlannerStatus');
    if (status) status.textContent = 'Calculating…';
    try {
      const result = await api(`api/v1/vintage/designation-simulate?year=${state.year}`, {method:'POST', body:JSON.stringify(lastPayload)});
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
    node.innerHTML = plans.length ? plans.map(plan => `<div class="list-row designation-plan-row"><span class="list-icon">§</span><div><b>${e(plan.wine_name)}</b><small>${e(plan.designation_label)} · ${e(plan.decision_status)} · legal ${e(String(plan.legal_review_status).replaceAll('_',' '))}</small><small>${Number(plan.projected_grapes_kg || 0).toLocaleString()} kg → ${Number(plan.projected_wine_l || 0).toLocaleString()} L → ${Number(plan.projected_bottles_750ml || 0).toLocaleString()} bottles</small></div></div>`).join('') : 'No saved designation decisions.';
  }

  function renderReconciliation() {
    const node = document.getElementById('designationReconciliation');
    if (!node) return;
    const draft = dashboard?.reconciliation_draft;
    node.classList.toggle('empty', !draft);
    if (!draft) { node.textContent = 'No reconciliation sheet is attached to this vintage.'; return; }
    node.innerHTML = `<p class="safety-note"><b>Review required.</b> ${e(draft.reporting_rule)}</p>
      ${(draft.working_actuals || []).map(row => `<div class="list-row"><div><b>${e(row.lot)} · ${Number(row.volume_l).toLocaleString()} L</b><small>${e(row.note)}</small></div></div>`).join('')}
      <details><summary>Calculations written on the sheet</summary>${(draft.source_calculations || []).map(row => `<p><b>${e(row.wine)}:</b> ${e(row.calculation)} <small>· ${e(row.confidence.replaceAll('_',' '))}</small></p>`).join('')}</details>`;
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
    }
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
