function socialPeople(rows, emptyText) {
  return rows.length
    ? rows.map(row => `<a href="${esc(row.profile_url || `https://www.instagram.com/${encodeURIComponent(row.username)}/`)}" target="_blank" rel="noopener"><b>@${esc(row.username)}</b><span>Review public profile ↗</span></a>`).join('')
    : `<p>${esc(emptyText)}</p>`;
}

function socialSigned(value, suffix = '') {
  const number = Number(value || 0);
  return `${number > 0 ? '+' : ''}${fmt(number)}${suffix}`;
}

function socialAuditMetric(label, value, note, tone = '') {
  return `<article class="${tone}"><span>${esc(label)}</span><strong>${esc(String(value))}</strong><small>${esc(note)}</small></article>`;
}

function renderSocialAudit(data) {
  const audience = data.audience || {}, relationship = data.relationships || {}, rel = relationship.summary || {};
  const summary = audience.summary || {}, coverage = audience.coverage || {}, stats = data.stats || {};
  const facebook = stats.facebook || {}, instagram = stats.instagram || {}, imports = relationship.imports || [];
  const currentFollowers = rel.followers ?? data.instagram?.account?.followers_count ?? 0;
  const currentFollowing = rel.following ?? data.instagram?.account?.follows_count ?? 0;
  const engagements = Number(facebook.total_engagements || 0) + Number(instagram.total_engagements || 0);
  const posts30 = Number(facebook.posts_30d || 0) + Number(instagram.posts_30d || 0);
  $('socialAuditMetrics').innerHTML = [
    socialAuditMetric('Instagram followers', fmt(currentFollowers), `${socialSigned(rel.follower_change || 0)} since prior official export`, Number(rel.follower_change || 0) < 0 ? 'loss' : 'gain'),
    socialAuditMetric('Following', fmt(currentFollowing), `${fmt(rel.mutual || 0)} mutual accounts`),
    socialAuditMetric('Follow-back rate', rel.follow_back_rate == null ? '—' : `${fmt(rel.follow_back_rate)}%`, `${fmt(rel.not_following_back || 0)} do not follow back`, rel.follow_back_rate != null && Number(rel.follow_back_rate) < 50 ? 'attention' : ''),
    socialAuditMetric('Net audience · 30d', socialSigned(summary.net_change_30d || 0), `+${fmt(summary.net_follows_30d || 0)} gained · −${fmt(summary.net_unfollows_30d || 0)} lost`, Number(summary.net_change_30d || 0) < 0 ? 'loss' : 'gain'),
    socialAuditMetric('Named changes', `${fmt(rel.new_followers || 0)} / ${fmt(rel.recent_unfollowers || 0)}`, 'new followers / unfollowers · latest comparison'),
    socialAuditMetric('Publishing · 30d', fmt(stats.published_30d || 0), `${fmt(stats.failed_30d || 0)} failed attempts`, Number(stats.failed_30d || 0) > 0 ? 'attention' : ''),
    socialAuditMetric('Recent post activity', fmt(posts30), `${fmt(engagements)} reactions, comments and shares in cache`),
    socialAuditMetric('Audit evidence', fmt(Number(coverage.snapshot_count || 0) + Number(rel.import_count || 0)), `${fmt(coverage.snapshot_count || 0)} API snapshots · ${fmt(rel.import_count || 0)} official imports`)
  ].join('');
  const cache = data.cache || {}, fbInsights = data.facebook?.insights || {}, igInsights = data.instagram?.insights || {};
  const trends = audience.trends || [], trendNode = $('socialAuditTrends');
  const insightRows = [['Instagram', igInsights], ['Facebook', fbInsights]].flatMap(([platform, insight]) => Object.entries(insight.metrics || {}).map(([metric, value]) => ({platform, metric, value})));
  trendNode.classList.toggle('empty', !trends.length && !insightRows.length);
  trendNode.innerHTML = (trends.length || insightRows.length)
    ? `${trends.length ? `<h4>90-day account movement</h4>${trends.map(row => `<div><span><b>${esc(row.platform)}</b><small>${fmt(row.samples_90d || 0)} measurements</small></span><strong class="${Number(row.change_90d || 0) < 0 ? 'loss' : 'gain'}">${socialSigned(row.change_90d || 0)}</strong><small>${row.growth_percent_90d == null ? 'baseline building' : socialSigned(row.growth_percent_90d, '%')}</small></div>`).join('')}` : ''}${insightRows.length ? `<h4 class="social-insights-heading">Supported Meta insights · 30d</h4>${insightRows.map(row => `<div><span><b>${esc(row.metric.split('_').join(' '))}</b><small>${esc(row.platform)}</small></span><strong>${fmt(row.value)}</strong><small>automatic</small></div>`).join('')}` : ''}`
    : 'Growth history will appear after snapshots accumulate.';
  const fresh = cache.last_checked_at ? timeLabel(cache.last_checked_at) : 'not checked';
  const latestImport = imports[0]?.imported_at ? timeLabel(imports[0].imported_at) : 'not imported';
  const health = $('socialAuditHealth');
  health.classList.remove('empty');
  health.innerHTML = `<h4>Audit source health</h4><div><span>Meta aggregate refresh</span><b>${esc(fresh)}</b></div><div><span>Named relationship export</span><b>${esc(latestImport)}</b></div><div><span>Export cadence</span><b class="${relationship.export_due ? 'attention' : 'good'}">${relationship.export_due ? 'due now' : 'current'}</b></div><div><span>Facebook insights</span><b class="${fbInsights.available ? 'good' : ''}">${fbInsights.available ? 'automatic' : 'optional / unavailable'}</b></div><div><span>Instagram insights</span><b class="${igInsights.available ? 'good' : ''}">${igInsights.available ? 'automatic' : 'optional / unavailable'}</b></div>`;
  const status = [];
  if (relationship.export_due) status.push('official export due');
  if (Number(stats.failed_30d || 0)) status.push(`${fmt(stats.failed_30d)} publish failure${Number(stats.failed_30d) === 1 ? '' : 's'}`);
  $('socialAuditStatus').textContent = status.length ? status.join(' · ') : 'Audit sources current';
  $('socialFollowersSummary').textContent = imports.length
    ? `${fmt(rel.followers || 0)} followers · ${fmt(rel.mutual || 0)} mutual · ${fmt(rel.not_following_back || 0)} not following back`
    : 'Snapshots, change history, named comparisons and official imports';
}

function renderSocialAudience(data) {
  const audience = data.audience || {}, summary = audience.summary || {}, relationships = data.relationships || {};
  const accounts = audience.accounts || [], events = audience.events || [], imports = relationships.imports || [];
  const accountNode = $('socialAudienceAccounts'), historyNode = $('socialAudienceHistory');
  renderSocialAudit(data);
  $('socialAudienceStatus').textContent = accounts.length ? `${accounts.length} account${accounts.length === 1 ? '' : 's'} stored · 90-day history` : 'Waiting for first live snapshot';
  accountNode.classList.toggle('empty', !accounts.length);
  accountNode.innerHTML = accounts.length ? accounts.map(row => `<article><span>${esc(row.platform)}</span><strong>${fmt(row.followers_count || 0)}</strong><small>followers · ${row.following_count == null ? 'following not supplied' : fmt(row.following_count) + ' following'}<br>Captured ${timeLabel(row.captured_at)}</small></article>`).join('') : 'No audience snapshots yet.';
  historyNode.classList.toggle('empty', !events.length);
  historyNode.innerHTML = `<div class="social-change-totals"><span><b>+${fmt(summary.net_follows_30d || 0)}</b><small>net gains · 30d</small></span><span><b>−${fmt(summary.net_unfollows_30d || 0)}</b><small>net losses · 30d</small></span><span><b>${socialSigned(summary.net_change_30d || 0)}</b><small>net change · 30d</small></span></div><div class="social-change-list">${events.length ? events.slice(0, 12).map(row => `<div class="${row.event_type === 'net_follow' ? 'gain' : 'loss'}"><b>${row.event_type === 'net_follow' ? '+' : '−'}${fmt(row.audience_change)}</b><span>${esc(row.platform)} · ${fmt(row.previous_count)} → ${fmt(row.current_count)}</span><time>${timeLabel(row.detected_at)}</time></div>`).join('') : '<p>No count change has been detected yet.</p>'}</div>`;
  $('socialAudienceNote').textContent = audience.identity_note || 'Meta provides aggregate audience totals; individual identities require an official account export.';
  const cadence = $('socialExportCadence'), due = Boolean(relationships.export_due);
  const next = relationships.next_export_due_at ? new Date(relationships.next_export_due_at).toLocaleDateString() : null;
  cadence.className = `social-export-cadence ${due ? 'due' : 'current'}`;
  cadence.innerHTML = `<div><b>${due ? 'Official export due' : 'Automatic 10-day check is current'}</b><span>${due ? 'Request the Followers and following JSON export in Meta Accounts Center. Once selected below, import and comparison are automatic.' : `Next official export due ${esc(next || 'in 10 days')}. Aggregate follower totals continue updating automatically.`}</span></div><a href="https://accountscenter.instagram.com/info_and_permissions/dyi/" target="_blank" rel="noopener">Open Accounts Center ↗</a>`;
  $('socialRelationshipSummary').classList.toggle('empty', !imports.length);
  $('socialRelationshipSummary').innerHTML = imports.length ? `<b>Latest import: ${fmt(imports[0].followers_count)} followers · ${fmt(imports[0].following_count)} following</b><span>${new Date(imports[0].imported_at).toLocaleString()} · ${esc(imports[0].source_filename || 'Meta export')}${imports.length > 1 ? ` · compared with ${new Date(imports[1].imported_at).toLocaleDateString()}` : ''}</span>` : 'No relationship export has been imported.';
  $('socialRecentFollowers').innerHTML = socialPeople(relationships.recent_followers || [], 'Import two exports to identify new followers.');
  $('socialRecentUnfollowers').innerHTML = socialPeople(relationships.recent_unfollowers || [], 'Import two exports to identify changes.');
  $('socialNotFollowingBack').innerHTML = socialPeople(relationships.not_following_back || [], 'Everyone in the import follows you back.');
  $('socialNotFollowedBack').innerHTML = socialPeople(relationships.not_followed_back || [], 'You follow everyone in the import.');
}

function bindSocialAudience() {
  const importer = $('socialAudienceImport');
  if (!importer) return;
  importer.onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter, data = new FormData(importer), file = data.get('file');
    if (!file?.size) return toast('Choose a Meta Instagram export');
    button.disabled = true; button.textContent = 'Importing…';
    try {
      const result = await formApi('api/v1/social/audience-import', data);
      state.social.relationships = result.relationships;
      renderSocialAudience(state.social);
      importer.reset();
      toast(`Imported ${result.followers} followers and ${result.following} following`);
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false; button.textContent = 'Import followers & following';
    }
  };
}
