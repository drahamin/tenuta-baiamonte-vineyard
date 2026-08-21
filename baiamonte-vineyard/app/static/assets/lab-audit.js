(function authoritativeLabAudit(){
  const baseRender=renderLabTrends;
  renderLabTrends=function(){
    baseRender();
    const audit=state.labTrends?.source_review,node=$('labCoverage');
    if(!audit||!node)return;
    const problems=Number(audit.missing_sample_count||0)+Number(audit.incomplete_or_wrong_count||0);
    node.querySelector('[data-lab-source-audit]')?.remove();
    node.insertAdjacentHTML('beforeend',`<article class="metric ${problems?'alert-metric':''}" data-lab-source-audit><span>Authoritative source audit</span><strong>${problems?`${problems} samples need review`:'Complete'}</strong><small>${Number(audit.source_reports_checked||0)} reports · ${Number(audit.authoritative_samples||0)} physical samples · ${(audit.duplicate_groups||[]).length} duplicate groups</small></article>`);
    const history=$('labHistoryList'),findings=audit.authoritative_findings||[];
    if(history&&findings.length&&!history.querySelector('[data-lab-audit-findings]'))history.insertAdjacentHTML('afterbegin',`<details class="panel muted-panel" data-lab-audit-findings open><summary>Authoritative report gaps · ${findings.length}</summary>${findings.map(row=>`<div class="list-row urgent"><span class="list-icon">!</span><div><b>${esc(row.sample_name)} · ${esc(row.report_date)}</b><small>${esc(String(row.status).replaceAll('_',' '))} · expected ${Number(row.expected_results)} results · stored ${Number(row.stored_results)}${row.vintage_year?` · vintage ${esc(row.vintage_year)}`:' · Annata blank; assignment needs review'}</small></div></div>`).join('')}</details>`);
  };
})();
