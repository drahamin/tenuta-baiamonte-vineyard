/* Operations water and off-grid energy workspaces. */
(function () {
  const fact = (label, value, note = '') => `<span><small>${esc(label)}</small><b>${esc(value ?? '—')}</b>${note ? `<em>${esc(note)}</em>` : ''}</span>`;
  const metric = (label, value, note = '', tone = '') => `<article class="metric ${tone}"><span>${esc(label)}</span><strong>${esc(value ?? '—')}</strong><small>${esc(note)}</small></article>`;
  const entityCards = rows => rows.length ? rows.map(row => `<article class="utility-entity ${row.available ? 'available' : 'unavailable'}"><i></i><div><b>${esc(row.name)}</b><small>${esc(row.entity_id)}</small></div><strong>${esc(row.state)}${row.unit ? ` ${esc(row.unit)}` : ''}</strong></article>`).join('') : '<div class="empty">No matching Home Assistant entities are available yet.</div>';
  const flowCards = rows => rows.map(row => `<article class="energy-flow-card ${esc(row.tone || '')}"><div><small>${esc(row.label)}</small><strong>${row.value_w != null ? `${fmt(row.value_w)} W` : row.value_kwh != null ? `${fmt(row.value_kwh)} kWh` : '—'}</strong><span>${esc(row.detail || '')}</span></div></article>`).join('');
  const stamp = value => value ? new Date(value).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : 'Not recorded';

  function drawSeries(canvas, points, accessors, colors, suffix = '') {
    if (!canvas) return;
    const ratio = Math.min(devicePixelRatio || 1, 2), width = canvas.clientWidth || 700, height = Number(canvas.getAttribute('height')) || 260;
    canvas.width = width * ratio; canvas.height = height * ratio;
    const context = canvas.getContext('2d'); context.scale(ratio, ratio); context.clearRect(0, 0, width, height);
    const pad = {left: 48, right: 16, top: 20, bottom: 30}, w = width - pad.left - pad.right, h = height - pad.top - pad.bottom;
    const values = points.flatMap(point => accessors.map(get => numeric(get(point))).filter(value => value != null));
    if (!values.length) { context.fillStyle = '#8c8982'; context.font = '14px sans-serif'; context.fillText('Waiting for numeric observations', pad.left, height / 2); return; }
    let min = Math.min(...values), max = Math.max(...values); if (min === max) { min -= 1; max += 1; }
    if (suffix === '%') { min = Math.max(0, min - 5); max = Math.min(100, max + 5); }
    context.strokeStyle = 'rgba(205,193,159,.16)'; context.fillStyle = '#8c8982'; context.font = '11px sans-serif';
    for (let i = 0; i < 4; i++) { const y = pad.top + h * i / 3; context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke(); context.fillText(`${Math.round((max - (max - min) * i / 3) * 10) / 10}${suffix}`, 2, y + 4); }
    const moments = points.map(point => Date.parse(point?.observed_at || ''));
    const timed = moments.length > 1 && moments.every(Number.isFinite) && Math.max(...moments) > Math.min(...moments);
    const firstMoment = timed ? Math.min(...moments) : 0, momentSpan = timed ? Math.max(...moments) - firstMoment : 0;
    accessors.forEach((get, series) => { context.strokeStyle = colors[series]; context.lineWidth = series ? 1.5 : 2.5; context.beginPath(); let started = false; points.forEach((point, index) => { const value = numeric(get(point)); if (value == null) { started = false; return; } const x = pad.left + (points.length === 1 ? w / 2 : timed ? w * (moments[index] - firstMoment) / momentSpan : w * index / (points.length - 1)), y = pad.top + h * (max - value) / (max - min); if (!started) { context.moveTo(x, y); started = true; } else context.lineTo(x, y); }); context.stroke(); });
    const first = points[0], last = points.at(-1); context.fillStyle = '#8c8982'; context.fillText(first?.observed_at ? stamp(first.observed_at) : 'Now', pad.left, height - 7); const label = last?.observed_at ? stamp(last.observed_at) : ''; context.fillText(label, Math.max(pad.left, width - pad.right - context.measureText(label).width), height - 7);
  }

  function renderWater(data) {
    const level = data.level || {}, learning = data.learning || {}, validation = learning.validation_metrics || {}, quality = learning.data_quality_snapshot || {}, history = data.history || [], historyQuality=data.history_quality||{}, attempt=data.latest_attempt||{}, confidence = numeric(level.confidence);
    $('waterFreshness').textContent = `Last accepted ${stamp(level.observed_at)} · pipeline checked ${stamp(attempt.attempted_at)}`;
    const volume=level.volume_projection||{},liters=numeric(volume.estimated_liters);
    $('waterKpis').innerHTML = [metric('Cistern level', level.calibrated&&numeric(level.level_percent) != null ? `${fmt(level.level_percent)}%` : 'Verify', level.label || 'Camera evidence', level.calibrated&&Number(level.level_percent) < 10 ? 'alert-metric' : ''), metric('Water available',liters==null?'Learning':`${fmt(liters)} L`,liters==null?`${Number(volume.calibration_deliveries||0)} of 2 delivery calibrations`:`${fmt(volume.estimated_liters_low)}–${fmt(volume.estimated_liters_high)} L`), metric('Reading confidence', confidence == null ? '—' : `${Math.round(confidence * 100)}%`, stamp(level.observed_at)), metric('Pipeline',attempt.status==='accepted'?'Accepted':attempt.status==='failed'?'Error':'Needs clear waterline',attempt.reason||'Awaiting next camera check',attempt.status==='accepted'?'':'alert-metric'), metric('Water equipment', data.health?.connected ?? 0, `${data.health?.unavailable || 0} unavailable`), metric('Learning status', String(learning.model_status || 'commissioning').replaceAll('_', ' '), `${learning.observation_count || 0} calibrated observations`)].join('');
    $('waterModelStatus').textContent = String(learning.model_status || 'Commissioning').replaceAll('_', ' ');
    const all = validation.all_history || validation.historical_backfill || {}, live = validation.live_shadow || {};
    $('waterLearning').innerHTML = [fact('Model', learning.model_version || 'cistern-door-volume-shadow-v3'), fact('All-history error', all.mae_points == null ? 'Learning' : `${fmt(all.mae_points)} points`), fact('New-view cases', live.cases || 0, '12 required'), fact('Distinct levels', quality.distinct_levels || 0, '4 required'), fact('Data through', stamp(learning.data_through)), fact('Authority', learning.model_status === 'validated' ? 'Eligible for bounded use' : 'Repositioned camera')].join('');
    $('waterLevelEvidence').innerHTML = `<span><i class="line gold"></i>Verified level</span><span><i class="line blue"></i>Reading confidence</span><b>${history.length} calibrated · ${Number(historyQuality.excluded_legacy||0)} legacy excluded</b>`;
    drawSeries($('waterLevelChart'), history, [row => row.level_percent, row => numeric(row.confidence) == null ? null : Number(row.confidence) * 100], ['#d9b735', '#6da7d9'], '%');
    $('waterEntityCount').textContent = `${data.health?.connected || 0} live`; $('waterEntities').innerHTML = entityCards(data.entities || []);
    $('waterFuture').innerHTML = (data.future_integrations || []).map(row => `<article><i>+</i><div><b>${esc(row.name)}</b><small>${esc(row.status)}</small></div></article>`).join('');
    $('openWaterSnapshot').onclick = () => window.openCisternSnapshot?.();
    $('saveWaterReference').onclick = async () => {
      const percent = numeric($('waterReferencePercent').value), confidencePercent = numeric($('waterReferenceConfidence').value);
      if (percent == null || percent < 0 || percent > 100) { $('waterReferenceStatus').textContent = 'Enter a level from 0 to 100%.'; return; }
      const button = $('saveWaterReference'); button.disabled = true; $('waterReferenceStatus').textContent = 'Saving calibrated evidence…';
      try {
        await api('api/v1/operations/water/cistern-reference', {method: 'POST', body: JSON.stringify({level_percent: percent, confidence: Math.max(0, Math.min(100, confidencePercent ?? 60)) / 100, notes: $('waterReferenceNotes').value})});
        $('waterReferenceStatus').textContent = `Saved ${fmt(percent)}% as owner-assisted evidence.`;
        await window.loadWaterWorkspace();
      } catch (error) { $('waterReferenceStatus').textContent = error.message; }
      finally { button.disabled = false; }
    };
    $('markWaterFull').onclick = async () => {
      if (!window.confirm('Confirm that the water surface in the latest retained frame is at the full line immediately below the access door. Save this frame as 100% full?')) return;
      const button = $('markWaterFull'); button.disabled = true; $('waterReferenceStatus').textContent = 'Saving the full-frame calibration…';
      try {
        await api('api/v1/operations/water/cistern-reference', {method: 'POST', body: JSON.stringify({level_percent: 100, confidence: 0.95, notes: 'Owner confirmed the current water surface is at the full line immediately below the access door; fixed corner geometry used and damp block-wall staining excluded.'})});
        $('waterReferenceStatus').textContent = 'Current retained frame saved as the 100% full reference.';
        await window.loadWaterWorkspace();
      } catch (error) { $('waterReferenceStatus').textContent = error.message; }
      finally { button.disabled = false; }
    };
    $('markWaterEmpty').onclick = async () => {
      if (!window.confirm('Confirm that the latest retained frame shows the cistern empty at the visible floor/base. Save this frame as 0% empty?')) return;
      const button = $('markWaterEmpty'); button.disabled = true; $('waterReferenceStatus').textContent = 'Saving the empty-frame calibration…';
      try {
        await api('api/v1/operations/water/cistern-reference', {method: 'POST', body: JSON.stringify({level_percent: 0, confidence: 0.95, notes: 'Owner confirmed the current frame shows the empty cistern floor/base; fixed corner geometry used and damp block-wall staining excluded.'})});
        $('waterReferenceStatus').textContent = 'Current retained frame saved as the 0% empty reference.';
        await window.loadWaterWorkspace();
      } catch (error) { $('waterReferenceStatus').textContent = error.message; }
      finally { button.disabled = false; }
    };
  }

  function renderSolar(data) {
    const solar = data.solar || {}, snap = data.snapshot || {}, bank = data.battery_bank || {}, model = data.learning || {}, overnight = data.overnight || {}, settings = data.settings || {}, power = Object.fromEntries((data.power || []).map(row => [row.code, row]));
    const current = numeric(solar.current_power?.value), today = numeric(solar.energy_today?.value), soc = numeric(snap.battery_soc_pct), load = numeric(snap.estate_load_w);
    $('solarFreshness').textContent = `Updated ${stamp(data.checked_at)} · ${data.battery_live ? 'batteries live' : 'checking battery link'}`;
    const loadNote = load == null ? 'Awaiting power inputs' : snap.load_method === 'measured' ? 'Main meter · high confidence' : `Calculated balance · ${snap.load_confidence || 'low'} confidence`;
    $('solarKpis').innerHTML = [metric('Solar now', current == null ? '—' : `${fmt(current)} W`, solar.current_power?.source || 'Awaiting Growatt'), metric('Energy today', today == null ? '—' : `${fmt(today)} kWh`, solar.energy_today?.source || 'Awaiting inverter'), metric('Battery', soc == null ? '—' : `${fmt(soc)}%`, power.battery?.detail || 'Awaiting RS485 telemetry', model.risk === 'critical' ? 'alert-metric' : ''), metric('Total load', load == null ? '—' : `${fmt(load)} W`, loadNote), metric('Tomorrow', solar.forecast_energy_tomorrow?.value == null ? '—' : `${fmt(solar.forecast_energy_tomorrow.value)} kWh`, 'Solcast P50')].join('');
    const coverage = numeric(overnight.coverage_pct), needed = numeric(overnight.energy_needed_kwh), charge = numeric(overnight.required_net_charge_w), gaugeCoverage = Math.max(0, Math.min(120, coverage || 0));
    $('overnightGauge').style.setProperty('--coverage', gaugeCoverage); $('overnightGaugeValue').textContent = coverage == null ? '—' : `${fmt(coverage)}%`; $('overnightGauge').setAttribute('aria-label', coverage == null ? 'Overnight energy coverage unavailable' : `Overnight energy coverage ${fmt(coverage)} percent`);
    $('overnightReadiness').dataset.state = coverage == null ? 'unknown' : coverage >= 100 ? 'ready' : coverage >= 70 ? 'watch' : 'short';
    $('overnightTitle').textContent = coverage == null ? 'Waiting for the battery forecast' : coverage >= 100 ? 'Enough power through sunrise' : `${fmt(needed)} kWh still needed`;
    $('overnightText').textContent = coverage == null ? 'The live battery or solar-clock sensor is not available yet.' : coverage >= 100 ? 'The bank can cover the forecast overnight demand and still retain the protected 30% reserve.' : `Continue adding an average ${fmt(charge)} W net to the batteries by the current solar deadline.`;
    $('overnightFacts').innerHTML = [fact('Stored target', overnight.target_energy_kwh == null ? '—' : `${fmt(overnight.target_energy_kwh)} kWh`), fact('Night demand', overnight.energy_required_kwh == null ? '—' : `${fmt(overnight.energy_required_kwh)} kWh`, '15% forecast margin'), fact('Still to add', needed == null ? '—' : `${fmt(needed)} kWh`), fact('Net charge needed', charge == null ? '—' : `${fmt(charge)} W`, 'By sunset / sunrise')].join('');
    $('energyGuard').dataset.risk = model.risk || 'unknown'; $('energyGuardTitle').textContent = model.risk === 'critical' ? 'Critical battery reserve' : model.risk === 'reserve' ? 'Reserve floor active' : soc == null ? 'Checking live battery link' : 'Live battery reserve protected';
    $('energyGuardText').textContent = soc == null ? 'Battery SOC is not connected yet. Automatic control is locked; missing telemetry is never interpreted as zero.' : model.estimated_hours_above_reserve == null ? `Battery is ${fmt(soc)}%. Learning the overnight estate load before calculating safe runtime.` : `${fmt(model.usable_above_reserve_kwh)} kWh above the ${fmt(settings.reserve_floor_pct)}% reserve · about ${fmt(model.estimated_hours_above_reserve)} hours at learned night demand.`;
    $('energyGuardBadge').textContent = model.control_enabled ? 'AUTO GUARDED' : data.battery_live ? 'LIVE · READ ONLY' : 'CHECK LINK'; $('energyModelStatus').textContent = String(model.status || 'learning').replaceAll('_', ' ');
    $('batteryBankConnection').textContent = bank.connected ? '2 / 2 ONLINE' : 'CHECK CONNECTION';
    $('batteryBankFacts').innerHTML = [fact('Bank status', bank.health == null ? 'Waiting' : `${String(bank.health).toUpperCase()} · ${bank.status || 'unknown'}`), fact('Stored energy', bank.remaining_kwh == null ? '—' : `${fmt(bank.remaining_kwh)} / ${fmt(bank.nominal_kwh)} kWh`), fact('Live DC', bank.power_w == null ? '—' : `${fmt(bank.power_w)} W · ${fmt(bank.voltage_v)} V · ${fmt(bank.current_a)} A`), fact('Battery 1', bank.packs?.[0]?.soc_pct == null ? 'Waiting' : `${fmt(bank.packs[0].soc_pct)}% · ${fmt(bank.packs[0].temperature_c)} °C · ${fmt(bank.packs[0].cell_spread_mv)} mV spread`), fact('Battery 2', bank.packs?.[1]?.soc_pct == null ? 'Waiting' : `${fmt(bank.packs[1].soc_pct)}% · ${fmt(bank.packs[1].temperature_c)} °C · ${fmt(bank.packs[1].cell_spread_mv)} mV spread`), fact('Bank balance', bank.soc_difference_pct == null ? '—' : `${fmt(bank.soc_difference_pct)}% SOC gap · ${fmt(bank.maximum_cell_spread_mv)} mV max spread`)].join('');
    $('energyLearning').innerHTML = [fact('Model', model.model || 'estate-energy-reserve-v1'), fact('Observed samples', model.observation_count || 0), fact('Night samples', model.night_observation_count || 0, '12 to establish baseline'), fact('Learned night load', model.learned_night_load_w == null ? 'Learning' : `${fmt(model.learned_night_load_w)} W`), fact('Reserve floor', `${fmt(settings.reserve_floor_pct)}%`), fact('Control authority', model.control_enabled ? 'Automatic · guarded' : model.control_eligible ? 'Eligible · disabled' : 'Locked')].join('');
    $('energySafety').textContent = data.safety_statement || '';
    const points = solar.forecast || []; $('solarSource').textContent = [solar.sources?.actual, solar.sources?.forecast].filter(Boolean).join(' + ') || 'Awaiting sources'; drawSeries($('solarUtilityChart'), points, [row => row.power_w, row => row.low_w, row => row.high_w], ['#d9b735', '#7c7564', '#f2d98c'], ' W');
    const range = solar.range_today || {}; $('solarRange').innerHTML = `<span><i class="line muted"></i>P10 ${range.low == null ? '—' : fmt(range.low) + ' kWh'}</span><span><i class="line gold"></i>P50 ${range.likely == null ? '—' : fmt(range.likely) + ' kWh'}</span><span><i class="line pale"></i>P90 ${range.high == null ? '—' : fmt(range.high) + ' kWh'}</span>`;
    const ready = (data.commissioning || []).filter(row => row.ready).length; $('energyCommissioningCount').textContent = `${ready} / ${(data.commissioning || []).length} ready`; $('energyCommissioning').innerHTML = (data.commissioning || []).map(row => `<article class="${row.ready ? 'ready' : 'waiting'}"><i>${row.ready ? '✓' : '○'}</i><div><b>${esc(row.name)}</b><small>${row.ready ? 'Connected and usable' : 'Awaiting verified entity / approval'}</small></div></article>`).join('');
    $('solarEntityCount').textContent = `${(data.energy_flow || []).filter(row => row.value_w != null || row.value_kwh != null).length} live`; $('solarEntities').innerHTML = flowCards(data.energy_flow || []);
  }

  window.loadWaterWorkspace = async function () { try { const data = await api('api/v1/operations/water'); state.waterWorkspace = data; renderWater(data); } catch (error) { $('waterFreshness').textContent = error.message; } };
  window.loadSolarWorkspace = async function () { try { const data = await api('api/v1/operations/solar'); state.solarWorkspace = data; renderSolar(data); } catch (error) { $('solarFreshness').textContent = error.message; } };
  window.addEventListener('resize', () => { if (document.querySelector('#view-water.active') && state.waterWorkspace) renderWater(state.waterWorkspace); if (document.querySelector('#view-solar.active') && state.solarWorkspace) renderSolar(state.solarWorkspace); }, {passive: true});
})();
