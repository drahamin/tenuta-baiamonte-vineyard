/* Side-by-side cistern learning presentation kept outside the core bundle. */
(function () {
  window.renderCisternLevel = function () {
    const level = state.systemStatus?.cistern_level || {};
    const percent = level.level_percent == null ? null : Number(level.level_percent);
    const confidence = level.confidence == null ? null : Math.round(Number(level.confidence) * 100);
    const learned = numeric(level.shadow_learning?.comparison?.predicted_level_percent);
    const metric = $('cisternMetric');
    $('cisternLevel').textContent = percent == null ? '—' : `${fmt(percent)}%`;
    $('cisternLevelDetail').textContent = [
      level.label || 'Camera AI estimate', confidence == null ? '' : `${confidence}% confidence`,
      learned == null ? '' : `shadow ${fmt(learned)}%`,
      level.observed_at ? `updated ${new Date(level.observed_at).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'})}` : 'initial value',
    ].filter(Boolean).join(' · ');
    metric?.classList.toggle('alert-metric', percent != null && percent < 10);
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
    $('recordDialogTitle').textContent = 'Latest cistern snapshot';
    $('recordDialogList').className = 'list';
    $('recordDialogList').innerHTML = `<section class="cistern-snapshot-view"><div class="cistern-snapshot-frame ${available ? '' : 'unavailable'}">${available ? `<img src="api/v1/cistern/snapshot?v=${encodeURIComponent(captured || Date.now())}" alt="Most recent cistern camera snapshot" onerror="this.closest('.cistern-snapshot-frame').classList.add('unavailable');this.remove()">` : '<span>◉</span><p>No camera image has been captured yet.</p>'}</div><div class="cistern-snapshot-facts"><span><small>Camera AI · active</small><b>${percent == null ? '—' : fmt(percent) + '%'}</b></span><span><small>Local learned · shadow</small><b>${learned == null ? 'Learning' : fmt(learned) + '%'}</b></span><span><small>Difference</small><b>${error == null ? 'Not scored' : fmt(error) + ' points'}</b></span><span><small>Camera confidence</small><b>${confidence == null ? 'Not available' : Math.round(confidence * 100) + '%'}</b></span><span><small>All-history error</small><b>${historical.mae_points == null ? 'Learning' : fmt(historical.mae_points) + ' points'}</b></span><span><small>New live evidence</small><b>${live.cases || 0} / 12</b></span><span><small>Captured</small><b>${captured ? esc(new Date(captured).toLocaleString()) : 'Not recorded'}</b></span></div><p class="safety-note">${validated ? 'The local model passed both historical and new-live gates and is eligible for bounded use. Camera AI remains the displayed source.' : 'Shadow mode: Camera AI remains authoritative. Historical agreement alone cannot release the learned model.'}</p>${level.notes ? `<p class="safety-note">${esc(level.notes)}</p>` : ''}</section>`;
    $('recordDialog').showModal();
  };
})();
