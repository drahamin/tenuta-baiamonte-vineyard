(() => {
  const byId = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));

  function age(value) {
    if (!value) return 'Never';
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 120) return `${seconds} sec`;
    if (seconds < 7200) return `${Math.round(seconds / 60)} min`;
    return `${Math.round(seconds / 3600)} h`;
  }

  function render(payload) {
    const config = payload.configuration || {}, status = payload.status || {}, form = byId('remoteErpForm');
    form.elements.url.value = config.url || '';
    form.elements.key_id.value = config.key_id || '';
    form.elements.snapshot_minutes.value = config.snapshot_minutes || 15;
    form.elements.enabled.checked = Boolean(config.enabled);
    form.elements.secret.value = '';
    const ready = config.enabled && config.secret_configured && !status.last_error;
    byId('remoteErpLights').innerHTML = `<div class="system-light ${ready?'green':config.enabled?'red':'amber'}"><i></i><span><b>Remote ERP</b><small>${ready?'Connected':config.enabled?'Needs attention':'Disabled'}</small></span></div><div class="system-light ${config.secret_configured?'green':'amber'}"><i></i><span><b>Sync key</b><small>${config.secret_configured?'Configured':'Owner handoff required'}</small></span></div>`;
    byId('remoteErpMetrics').innerHTML = `<article class="metric"><span>Reporting scope</span><strong>${Number(config.object_count||58)}</strong><small>approved objects</small></article><article class="metric"><span>Last successful sync</span><strong>${safe(age(status.last_success_at))}</strong><small>${safe(status.last_success_at||'No snapshot received')}</small></article><article class="metric"><span>Records copied</span><strong>${Number(status.record_count||0).toLocaleString()}</strong><small>atomic active snapshot</small></article><article class="metric"><span>Data age</span><strong>${safe(age(status.last_success_at))}</strong><small>${status.last_error?safe(status.last_error):'No reported error'}</small></article>`;
    byId('remoteErpQueueStatus').textContent = status.last_success_at ? 'Snapshot transport verified · command validation remains separately gated' : 'Waiting for first verified snapshot';
  }

  async function load() {
    const payload = await api('api/v1/admin/remote-erp');
    render(payload);
  }

  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget, data = new FormData(form), button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const payload = {url:data.get('url'),key_id:data.get('key_id'),secret:data.get('secret'),snapshot_minutes:Number(data.get('snapshot_minutes')),enabled:data.get('enabled')==='on'};
      const result = await api('api/v1/admin/remote-erp',{method:'PUT',headers:{'X-Baiamonte-CSRF':'same-origin'},body:JSON.stringify(payload)});
      render({configuration:result.configuration,status:{}});
      byId('remoteErpMessage').textContent = 'Remote ERP settings saved and audited.';
      await load();
    } catch (error) { byId('remoteErpMessage').textContent = error.message; }
    finally { button.disabled = false; }
  }

  async function run() {
    const button = byId('remoteErpRun'); button.disabled = true;
    try {
      byId('remoteErpMessage').textContent = 'Building a consistent 58-object snapshot…';
      await api('api/v1/admin/remote-erp/run',{method:'POST',headers:{'X-Baiamonte-CSRF':'same-origin'},body:'{}'});
      byId('remoteErpMessage').textContent = 'Snapshot delivered and activated.';
      await load();
    } catch (error) { byId('remoteErpMessage').textContent = error.message; }
    finally { button.disabled = false; }
  }

  window.loadRemoteErp = load;
  byId('remoteErpForm')?.addEventListener('submit', save);
  byId('remoteErpRefresh')?.addEventListener('click', () => load().catch(error => byId('remoteErpMessage').textContent = error.message));
  byId('remoteErpRun')?.addEventListener('click', run);
})();
