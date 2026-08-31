/* Side-by-side cistern learning presentation kept outside the core bundle. */
(function () {
  window.renderCisternLevel = function () {
    const level = state.systemStatus?.cistern_level || {};
    const percent = level.level_percent == null ? null : Number(level.level_percent);
    const confidence = level.confidence == null ? null : Math.round(Number(level.confidence) * 100);
    const learned = numeric(level.shadow_learning?.comparison?.predicted_level_percent);
    const metric = $('cisternMetric');
    const volume = level.volume_projection || {}, liters = numeric(volume.estimated_liters);
    $('cisternLevel').textContent = level.calibrated && percent != null ? `${fmt(percent)}%` : 'Verify';
    $('cisternLevelDetail').textContent = [
      level.label || 'Camera AI estimate', liters == null ? 'liters learning' : `${fmt(liters)} L available`, confidence == null ? '' : `${confidence}% confidence`,
      learned == null ? '' : `shadow ${fmt(learned)}%`,
      level.observed_at ? `updated ${new Date(level.observed_at).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'})}` : 'initial value',
    ].filter(Boolean).join(' · ');
    metric?.classList.toggle('alert-metric', Boolean(level.calibrated) && percent != null && percent < 10);
    if (metric) metric.onclick = openCisternSnapshot;
  };

  window.openCisternSnapshot = function () {
    const level = state.systemStatus?.cistern_level || {};
    const percent = numeric(level.level_percent), confidence = numeric(level.confidence);
    const captured = level.snapshot_captured_at || level.observed_at, available = Boolean(level.snapshot_available);
    const comparison = level.shadow_learning?.comparison || {}, model = level.shadow_learning?.model || {};
    const learned = numeric(comparison.predicted_level_percent), error = numeric(comparison.absolute_error_points);
    const validation = model.validation_metrics || {}, historical = validation.all_history || validation.historical_backfill || {}, live = validation.live_shadow || {};
    const validated = model.model_status === 'validated';
    const volume = level.volume_projection || {}, liters = numeric(volume.estimated_liters);
    $('recordDialogTitle').textContent = 'Latest cistern snapshot';
    $('recordDialogList').className = 'list';
    $('recordDialogList').innerHTML = `<section class="cistern-snapshot-view"><div class="cistern-snapshot-frame ${available ? '' : 'unavailable'}">${available ? `<img src="api/v1/cistern/snapshot?v=${encodeURIComponent(captured || Date.now())}" alt="Most recent cistern camera snapshot" onerror="this.closest('.cistern-snapshot-frame').classList.add('unavailable');this.remove()">` : '<span>◉</span><p>No camera image has been captured yet.</p>'}</div><div class="cistern-snapshot-facts"><span><small>Door-calibrated level</small><b>${level.calibrated&&percent != null ? fmt(percent) + '%' : 'Needs verification'}</b></span><span><small>Water available</small><b>${liters == null ? 'Learning liters' : `${fmt(liters)} L`}</b></span><span><small>Estimated range</small><b>${liters == null ? `${Number(volume.calibration_deliveries||0)} / 2 deliveries` : `${fmt(volume.estimated_liters_low)}–${fmt(volume.estimated_liters_high)} L`}</b></span><span><small>Local trend · shadow only</small><b>${learned == null ? 'Learning' : fmt(learned) + '%'}</b></span><span><small>Trend difference</small><b>${error == null ? 'Not scored' : fmt(error) + ' points'}</b></span><span><small>Camera confidence</small><b>${confidence == null ? 'Not available' : Math.round(confidence * 100) + '%'}</b></span><span><small>Agreement with prior AI</small><b>${historical.mae_points == null ? 'Learning' : fmt(historical.mae_points) + ' points'}</b></span><span><small>Physical reference checks</small><b>${Number(model.data_quality_snapshot?.physical_reference_labels || 0)} / 3</b></span><span><small>Captured</small><b>${captured ? esc(new Date(captured).toLocaleString()) : 'Not recorded'}</b></span></div><p class="safety-note">Full is immediately below the upper access door. The waterline is measured between that mark and the visible floor; darkness, wet wall areas and glare are ignored.</p><p class="safety-note">${esc(volume.note||'Each confirmed 5,000 L Nunzio delivery supplies a physical calibration delta for the liters model.')}</p><p class="safety-note">${validated ? 'Trend validation passed, but physical reference checks are still required before this is treated as gauge accuracy.' : 'Shadow mode: agreement with earlier camera-AI estimates is not physical accuracy. Use the camera image and verified level references for decisions.'}</p>${level.notes ? `<p class="safety-note">${esc(level.notes)}</p>` : ''}</section>`;
    $('recordDialog').showModal();
  };
})();
