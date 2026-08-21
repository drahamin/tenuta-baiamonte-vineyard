function renderSystemDocs(){
  const data=state.systemDocs
  if(!data)return
  $('systemDocsVersion').textContent=`v${data.version||'—'}`
  $('systemDocsSummary').textContent=`${(data.services||[]).length} services · ${(data.api_groups||[]).reduce((sum,group)=>sum+(group.routes||[]).length,0)} documented routes · generated ${dateLabel(data.generated_at)}`
  $('systemDocsServices').classList.remove('empty')
  $('systemDocsServices').innerHTML=(data.services||[]).map(service=>`<div class="system-doc-row"><div><b>${esc(service.name)}</b><small>${esc(service.purpose||'')}</small><small>${esc(service.access||'')}</small></div><span class="system-doc-port">${service.port?`:${esc(service.port)}`:'internal'}</span>${service.url?`<a href="${esc(service.url)}" target="_blank" rel="noopener">Open</a>`:''}</div>`).join('')||'<p>No services are registered.</p>'
  $('systemDocsCredentials').classList.remove('empty')
  $('systemDocsCredentials').innerHTML=(data.credentials||[]).map(item=>{
    const optional=['Facebook','Instagram'].includes(item.name)
    const stateClass=item.configured?'good':optional?'optional':'missing'
    const label=item.configured?'Configured':optional?'Not configured':'Needs setup'
    return `<div class="system-credential ${stateClass}"><i></i><div><b>${esc(item.name)}</b><small>${label} · ${esc(item.location||'')}</small></div></div>`
  }).join('')||'<p>No protected connections are registered.</p>'
  $('systemDocsApis').classList.remove('empty')
  $('systemDocsApis').innerHTML=(data.api_groups||[]).map(group=>`<section class="system-api-group"><h4>${esc(group.name)}</h4>${(group.routes||[]).map(route=>`<div class="system-api-row"><span class="system-method">${esc(route.method)}</span><code>${esc(route.path)}</code><span>${esc(route.purpose)}</span><small>${esc(route.access)}</small></div>`).join('')}</section>`).join('')
  $('systemDocsAccess').classList.remove('empty')
  $('systemDocsAccess').innerHTML=(data.access_profiles||[]).map(profile=>`<div class="system-doc-row"><div><b>${esc(profile.name)}</b><small>${esc(profile.scope||'')}</small><div class="system-access-users">${(profile.users||[]).map(user=>`<span class="system-access-chip">${esc(user)}</span>`).join('')||'<span class="system-access-chip muted">None configured</span>'}</div></div></div>`).join('')
  $('systemDocsLinks').classList.remove('empty')
  $('systemDocsLinks').innerHTML=(data.links||[]).map(link=>`<a class="system-doc-row system-doc-link" href="${esc(link.url)}" target="${String(link.url).startsWith('http')?'_blank':'_top'}" rel="noopener"><div><b>${esc(link.name)}</b><small>${esc(link.purpose||'')}</small></div><span>Open →</span></a>`).join('')
  $('systemDocsNotes').innerHTML=(data.notes||[]).map(note=>`<p>${esc(note)}</p>`).join('')
}
