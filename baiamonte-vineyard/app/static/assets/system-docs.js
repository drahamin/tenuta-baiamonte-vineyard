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
  renderOfficialDocuments()
}

function renderOfficialDocuments(){
  const data=state.systemDocs||{},all=data.official_documents||[],query=String($('officialDocsSearch')?.value||'').trim().toLowerCase(),type=$('officialDocsType')?.value||''
  const rows=all.filter(row=>(!type||row.document_type===type)&&(!query||[row.title,row.summary,row.issuing_authority,row.reference_number,row.original_filename].some(value=>String(value||'').toLowerCase().includes(query))))
  if($('officialDocsStats'))$('officialDocsStats').innerHTML=[['Documents',all.length],['Current',all.filter(row=>row.status==='current').length],['Reference only',all.filter(row=>row.status==='reference').length],['Atlas linked',all.filter(row=>(row.related_scope?.domains||[]).includes('atlas')).length]].map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')
  if(!$('officialDocsList'))return
  $('officialDocsList').classList.toggle('empty',!rows.length)
  $('officialDocsList').innerHTML=rows.map(row=>{const facts=row.verified_facts||{},scope=row.related_scope||{},factText=Object.entries(facts).slice(0,5).map(([key,value])=>`${key.replaceAll('_',' ')}: ${value}`).join(' · '),scopeText=[...(scope.parcels||[]),...(scope.vintages||[]),...(scope.varieties||[])].join(' · ');return `<article class="official-document-card"><div class="official-document-heading"><div><span class="status-chip ${esc(row.status)}">${esc(row.status)}</span><h4>${esc(row.title)}</h4><small>${esc(row.issuing_authority||'Authority not recorded')}${row.issue_date?` · ${esc(row.issue_date)}`:''}${row.reference_number?` · ${esc(row.reference_number)}`:''}</small></div><div class="button-row"><a class="button-link" href="${esc(row.view_url)}" target="_blank" rel="noopener">View</a><a class="button-link secondary" href="${esc(row.download_url)}" download>Download</a></div></div><p>${esc(row.summary||'No summary recorded.')}</p>${factText?`<small class="official-document-facts">${esc(factText)}</small>`:''}${scopeText?`<small class="official-document-scope">Linked: ${esc(scopeText)}</small>`:''}</article>`}).join('')||'<p>No official documents match this filter.</p>'
}
