/* Operations water and off-grid energy workspaces. */
(function () {
  const fact = (label, value, note = '') => `<span><small>${esc(label)}</small><b>${esc(value ?? '—')}</b>${note ? `<em>${esc(note)}</em>` : ''}</span>`;
  const metric = (label, value, note = '', tone = '') => `<article class="metric ${tone}"><span>${esc(label)}</span><strong>${esc(value ?? '—')}</strong><small>${esc(note)}</small></article>`;
  const entityCards = rows => rows.length ? rows.map(row => `<article class="utility-entity ${row.available ? 'available' : 'unavailable'}"><i></i><div><b>${esc(row.name)}</b><small>${esc(row.entity_id)}</small></div><strong>${esc(row.state)}${row.unit ? ` ${esc(row.unit)}` : ''}</strong></article>`).join('') : '<div class="empty">No matching Home Assistant entities are available yet.</div>';
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
    accessors.forEach((get, series) => { context.strokeStyle = colors[series]; context.lineWidth = series ? 1.5 : 2.5; context.beginPath(); let started = false; points.forEach((point, index) => { const value = numeric(get(point)); if (value == null) return; const x = pad.left + (points.length === 1 ? w / 2 : w * index / (points.length - 1)), y = pad.top + h * (max - value) / (max - min); if (!started) { context.moveTo(x, y); started = true; } else context.lineTo(x, y); }); context.stroke(); });
    const first = points[0], last = points.at(-1); context.fillStyle = '#8c8982'; context.fillText(first?.observed_at ? stamp(first.observed_at) : 'Now', pad.left, height - 7); const label = last?.observed_at ? stamp(last.observed_at) : ''; context.fillText(label, Math.max(pad.left, width - pad.right - context.measureText(label).width), height - 7);
  }

  function renderWater(data) {
    const level = data.level || {}, learning = data.learning || {}, validation = learning.validation_metrics || {}, quality = learning.data_quality_snapshot || {}, history = data.history || [], confidence = numeric(level.confidence);
    $('waterFreshness').textContent = `Updated ${stamp(data.checked_at)} · ${data.health?.connected || 0} connected`;
    const volume=level.volume_projection||{},liters=numeric(volume.estimated_liters);
    $('waterKpis').innerHTML = [metric('Cistern level', level.calibrated&&numeric(level.level_percent) != null ? `${fmt(level.level_percent)}%` : 'Verify', level.label || 'Camera evidence', level.calibrated&&Number(level.level_percent) < 10 ? 'alert-metric' : ''), metric('Water available',liters==null?'Learning':`${fmt(liters)} L`,liters==null?`${Number(volume.calibration_deliveries||0)} of 2 delivery calibrations`:`${fmt(volume.estimated_liters_low)}–${fmt(volume.estimated_liters_high)} L`), metric('Reading confidence', confidence == null ? '—' : `${Math.round(confidence * 100)}%`, stamp(level.observed_at)), metric('Water entities', data.health?.connected ?? 0, `${data.health?.unavailable || 0} unavailable`), metric('Learning status', String(learning.model_status || 'commissioning').replaceAll('_', ' '), `${learning.observation_count || 0} observations`)].join('');
    $('waterModelStatus').textContent = String(learning.model_status || 'Commissioning').replaceAll('_', ' ');
    const all = validation.all_history || validation.historical_backfill || {}, live = validation.live_shadow || {};
    $('waterLearning').innerHTML = [fact('Model', learning.model_version || 'cistern-door-volume-shadow-v2'), fact('All-history error', all.mae_points == null ? 'Learning' : `${fmt(all.mae_points)} points`), fact('New live cases', live.cases || 0, '12 required'), fact('Distinct levels', quality.distinct_levels || 0, '4 required'), fact('Data through', stamp(learning.data_through)), fact('Authority', learning.model_status === 'validated' ? 'Eligible for bounded use' : 'Camera AI')].join('');
    $('waterLevelEvidence').innerHTML = `<span><i class="line gold"></i>Camera level</span><span><i class="line blue"></i>Confidence × 100</span><b>${history.length} retained readings</b>`;
    drawSeries($('waterLevelChart'), history, [row => row.level_percent, row => numeric(row.confidence) == null ? null : Number(row.confidence) * 100], ['#d9b735', '#6da7d9'], '%');
    $('waterEntityCount').textContent = `${data.health?.connected || 0} live`; $('waterEntities').innerHTML = entityCards(data.entities || []);
    $('waterFuture').innerHTML = (data.future_integrations || []).map(row => `<article><i>+</i><div><b>${esc(row.name)}</b><small>${esc(row.status)}</small></div></article>`).join('');
    $('openWaterSnapshot').onclick = () => window.openCisternSnapshot?.();
  }

  function renderSolar(data) {
    const solar = data.solar || {}, snap = data.snapshot || {}, model = data.learning || {}, settings = data.settings || {}, power = Object.fromEntries((data.power || []).map(row => [row.code, row]));
    const current = numeric(solar.current_power?.value), today = numeric(solar.energy_today?.value), soc = numeric(snap.battery_soc_pct), load = numeric(snap.estate_load_w);
    $('solarFreshness').textContent = `Updated ${stamp(data.checked_at)} · ${data.commissioning_ready ? 'commissioned' : 'commissioning'}`;
    $('solarKpis').innerHTML = [metric('Solar now', current == null ? '—' : `${fmt(current)} W`, solar.current_power?.source || 'Awaiting Growatt'), metric('Energy today', today == null ? '—' : `${fmt(today)} kWh`, solar.energy_today?.source || 'Awaiting inverter'), metric('Battery', soc == null ? '—' : `${fmt(soc)}%`, power.battery?.detail || 'Awaiting CAN telemetry', model.risk === 'critical' ? 'alert-metric' : ''), metric('Estate load', load == null ? '—' : `${fmt(load)} W`, load == null ? 'Awaiting load meter' : 'Live demand'), metric('Tomorrow', solar.forecast_energy_tomorrow?.value == null ? '—' : `${fmt(solar.forecast_energy_tomorrow.value)} kWh`, 'Solcast P50')].join('');
    $('energyGuard').dataset.risk = model.risk || 'unknown'; $('energyGuardTitle').textContent = model.risk === 'critical' ? 'Critical battery reserve' : model.risk === 'reserve' ? 'Reserve floor active' : soc == null ? 'Commissioning reserve protection' : 'Battery reserve protected';
    $('energyGuardText').textContent = soc == null ? 'Battery SOC is not connected yet. Automatic control is locked; missing telemetry is never interpreted as zero.' : model.estimated_hours_above_reserve == null ? `Battery is ${fmt(soc)}%. Learning the overnight estate load before calculating safe runtime.` : `${fmt(model.usable_above_reserve_kwh)} kWh above the ${fmt(settings.reserve_floor_pct)}% reserve · about ${fmt(model.estimated_hours_above_reserve)} hours at learned night demand.`;
    $('energyGuardBadge').textContent = model.control_enabled ? 'AUTO GUARDED' : 'SHADOW'; $('energyModelStatus').textContent = String(model.status || 'commissioning').replaceAll('_', ' ');
    $('energyLearning').innerHTML = [fact('Model', model.model || 'estate-energy-reserve-v1'), fact('Observed samples', model.observation_count || 0), fact('Night samples', model.night_observation_count || 0, '12 to establish baseline'), fact('Learned night load', model.learned_night_load_w == null ? 'Learning' : `${fmt(model.learned_night_load_w)} W`), fact('Reserve floor', `${fmt(settings.reserve_floor_pct)}%`), fact('Control authority', model.control_enabled ? 'Automatic · guarded' : model.control_eligible ? 'Eligible · disabled' : 'Locked')].join('');
    $('energySafety').textContent = data.safety_statement || '';
    const points = solar.forecast || []; $('solarSource').textContent = [solar.sources?.actual, solar.sources?.forecast].filter(Boolean).join(' + ') || 'Awaiting sources'; drawSeries($('solarUtilityChart'), points, [row => row.power_w, row => row.low_w, row => row.high_w], ['#d9b735', '#7c7564', '#f2d98c'], ' W');
    const range = solar.range_today || {}; $('solarRange').innerHTML = `<span><i class="line muted"></i>P10 ${range.low == null ? '—' : fmt(range.low) + ' kWh'}</span><span><i class="line gold"></i>P50 ${range.likely == null ? '—' : fmt(range.likely) + ' kWh'}</span><span><i class="line pale"></i>P90 ${range.high == null ? '—' : fmt(range.high) + ' kWh'}</span>`;
    const ready = (data.commissioning || []).filter(row => row.ready).length; $('energyCommissioningCount').textContent = `${ready} / ${(data.commissioning || []).length} ready`; $('energyCommissioning').innerHTML = (data.commissioning || []).map(row => `<article class="${row.ready ? 'ready' : 'waiting'}"><i>${row.ready ? '✓' : '○'}</i><div><b>${esc(row.name)}</b><small>${row.ready ? 'Connected and usable' : 'Awaiting verified entity / approval'}</small></div></article>`).join('');
    $('solarEntityCount').textContent = `${(data.entities || []).filter(row => row.available).length} live`; $('solarEntities').innerHTML = entityCards(data.entities || []);
  }

  window.loadWaterWorkspace = async function () { try { const data = await api('api/v1/operations/water'); state.waterWorkspace = data; renderWater(data); } catch (error) { $('waterFreshness').textContent = error.message; } };
  window.loadSolarWorkspace = async function () { try { const data = await api('api/v1/operations/solar'); state.solarWorkspace = data; renderSolar(data); } catch (error) { $('solarFreshness').textContent = error.message; } };
  window.addEventListener('resize', () => { if (document.querySelector('#view-water.active') && state.waterWorkspace) renderWater(state.waterWorkspace); if (document.querySelector('#view-solar.active') && state.solarWorkspace) renderSolar(state.solarWorkspace); }, {passive: true});
})();
