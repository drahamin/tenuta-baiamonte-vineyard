function intakeSourcePreview(item,id,compact=false){
  const mime=String(item?.media_type||'')
  const url=`api/v1/intake/${encodeURIComponent(id)}/file`
  const name=item?.original_filename||'Original source'
  const viewer=mime.startsWith('image/')
    ?`<img src="${url}" alt="${esc(name)}">`
    :mime==='application/pdf'||String(name).toLowerCase().endsWith('.pdf')
      ?`<iframe src="${url}#view=FitH" title="${esc(name)}"></iframe>`
      :'<p>Preview is not available for this file type. Open or download the original.</p>'
  return `<details class="intake-source-review ${compact?'compact':''}" open>
    <summary><span><b>Original source · ${esc(name)}</b><small>Compare every sample heading, wine, value and unit before approval.</small></span></summary>
    <div class="intake-source-actions">
      <a class="button-link" href="${url}" target="_blank" rel="noopener">View original</a>
      <a class="button-link secondary" href="${url}?download=true">Download</a>
      ${compact?'':`<button type="button" class="secondary" data-reanalyze-intake="${esc(id)}">Reanalyze and separate samples</button>`}
    </div>${viewer}</details>`
}

const openIntakeReviewWithoutSource=openIntakeReview
openIntakeReview=async function(id){
  await openIntakeReviewWithoutSource(id)
  if(!$('intakeDialog')?.open)return
  try{
    const item=await api(`api/v1/intake/${id}`)
    state.intakeSource=item
    $('intakeDetail')?.insertAdjacentHTML('afterbegin',intakeSourcePreview(item,id))
    const linkedNames=new Set((item.linked_records||[]).map(row=>String(row.sample_name||'').trim().toLowerCase()).filter(Boolean))
    ;(state.intakeDraft||[]).forEach((record,index)=>{
      const button=$('intakeDetail')?.querySelector(`[data-use-intake="${index}"]`)
      const fields=record.fields||record.values||{}
      const results=Array.isArray(fields.results)?fields.results:[]
      const type=intakeType(record.destination_section||record.section||record.record_type)
      const sampleName=String(fields.sample_name||fields.source_sample_label||`sample ${index+1}`).trim()
      if(!button||type!=='lab')return
      const alreadySaved=linkedNames.has(sampleName.toLowerCase())
      button.textContent=`${alreadySaved?'Saved':'Review'} ${sampleName} · ${results.length} result${results.length===1?'':'s'}`
      button.disabled=alreadySaved
      button.onclick=()=>{if(!alreadySaved){$('intakeDialog').close();openEntry('lab',fields,id)}}
    })
    const remaining=$('intakeDetail')?.querySelectorAll('[data-use-intake]:not(:disabled)').length||0
    if(item.linked_records?.length&&remaining){
      $('intakeDetail')?.querySelector('.intake-actions')?.insertAdjacentHTML('beforebegin',`<p class="intake-progress">${item.linked_records.length} sample${item.linked_records.length===1?'':'s'} saved · review ${remaining} remaining.</p>`)
    }
    const reanalyze=$('intakeDetail')?.querySelector('[data-reanalyze-intake]')
    if(reanalyze)reanalyze.onclick=async()=>{
      reanalyze.disabled=true
      reanalyze.textContent='Reanalyzing…'
      try{
        await api(`api/v1/intake/${id}/analyze`,{method:'POST',body:'{}'})
        $('intakeDialog').close()
        await openIntakeReview(id)
        toast('Source reanalyzed and separated for review')
      }catch(error){
        toast(error.message)
        reanalyze.disabled=false
        reanalyze.textContent='Reanalyze and separate samples'
      }
    }
  }catch(error){toast(`Original source could not be loaded: ${error.message}`)}
}

const openEntryWithoutIntakeSource=openEntry
openEntry=function(type,draft=null,intakeId=null){
  openEntryWithoutIntakeSource(type,draft,intakeId)
  if(intakeId&&state.intakeSource)$('formFields')?.insertAdjacentHTML('afterbegin',intakeSourcePreview(state.intakeSource,intakeId,true))
}
