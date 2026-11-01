/* SOURCE DISABLED: not referenced by index.html until the narrow activation review. */
(()=>{
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))
  const measurements=payload=>(payload.measurements||[]).map(row=>`<li><b>${escape(row.code)}</b><span>${escape(row.value)} ${escape(row.unit)}</span></li>`).join('')
  const evidence=report=>`api/v1/mobile-intake/${encodeURIComponent(report.report_uuid)}/attachments`
  function card(report){
    let payload={};try{payload=typeof report.payload_json==='string'?JSON.parse(report.payload_json):report.payload_json||{}}catch{}
    return `<article class="mobile-review-card" data-mobile-review="${escape(report.report_uuid)}">
      <header><div><small>RECEIVED FOR REVIEW · NOT APPLIED</small><h3>${escape(payload.entities?.container_id||'Cellar reading')}</h3></div><span>rev ${escape(report.revision)}</span></header>
      <p>${escape(new Date(report.occurred_at).toLocaleString())} · submitted by ${escape(report.actor_username)}</p>
      <ul>${measurements(payload)}</ul><p>${escape(payload.note||'No note supplied')}</p>
      <div class="mobile-review-evidence" data-review-evidence="${escape(report.report_uuid)}"><button type="button">Load private evidence</button></div>
      <label>Independent review note<textarea maxlength="2000" required placeholder="State what was checked and why"></textarea></label>
      <footer><button data-decision="approved">Approve report</button><button class="secondary" data-decision="correction_required">Request correction</button><button class="danger" data-decision="rejected">Reject</button></footer>
      <p class="mobile-review-boundary">This decision classifies the immutable report only. It does not change a tank reading, wine lot, inventory, payroll, or device.</p>
    </article>`
  }
  async function loadEvidence(node,reportUuid){
    const result=await api(evidence({report_uuid:reportUuid}));const rows=result.attachments||[]
    node.innerHTML=rows.length?rows.map(row=>`<a href="${escape(row.preview_url)}" target="_blank" rel="noopener">${escape(row.original_filename||'Evidence')}</a>`).join(''):'<small>No evidence attached</small>'
  }
  async function decide(cardNode,status){
    const note=cardNode.querySelector('textarea').value.trim(),reportUuid=cardNode.dataset.mobileReview,revision=cardNode.querySelector('header span').textContent.replace('rev ','')
    if(!note){toast('An independent review note is required');return}
    cardNode.querySelectorAll('button').forEach(button=>button.disabled=true)
    try{
      const result=await api(`api/v1/mobile-intake/${encodeURIComponent(reportUuid)}/decision`,{method:'PATCH',headers:{'X-Baiamonte-Expected-Revision':revision},body:JSON.stringify({review_status:status,review_note:note})})
      toast(`${result.review_status.replaceAll('_',' ')} · receipt pending delivery · no business record applied`);cardNode.remove()
    }catch(error){toast(error.message);cardNode.querySelectorAll('button').forEach(button=>button.disabled=false)}
  }
  async function loadInitialMobileReview(){
    const host=document.querySelector('#mobileIntakeReviewQueue');if(!host)return
    const result=await api('api/v1/mobile-intake/initial-enology-review');host.innerHTML=(result.reports||[]).map(card).join('')||'<p class="empty">No configured-author enology readings are waiting for independent review.</p>'
    host.querySelectorAll('[data-review-evidence] button').forEach(button=>button.onclick=()=>loadEvidence(button.parentElement,button.parentElement.dataset.reviewEvidence).catch(error=>toast(error.message)))
    host.querySelectorAll('[data-decision]').forEach(button=>button.onclick=()=>decide(button.closest('[data-mobile-review]'),button.dataset.decision))
  }
  window.loadInitialMobileReview=loadInitialMobileReview
})()
