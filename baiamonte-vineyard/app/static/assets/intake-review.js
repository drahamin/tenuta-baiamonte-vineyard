function intakeSourcePreview(item,id,compact=false){
  const mime=String(item?.media_type||'')
  const url=`api/v1/intake/${encodeURIComponent(id)}/file`
  const previewUrl=`api/v1/intake/${encodeURIComponent(id)}/preview`
  const name=item?.original_filename||'Original source'
  const viewer=mime.startsWith('image/')
    ?`<img src="${url}" alt="${esc(name)}">`
    :mime==='application/pdf'||String(name).toLowerCase().endsWith('.pdf')
      ?`<a class="intake-pdf-preview" href="${url}" target="_blank" rel="noopener"><img src="${previewUrl}" alt="First page of ${esc(name)}"><span>Open the complete PDF</span></a>`
      :'<p>Preview is not available for this file type. Open or download the original.</p>'
  return `<details class="intake-source-review ${compact?'compact':''}" open>
    <summary><span><b>Original source · ${esc(name)}</b><small>Compare every sample heading, wine, value and unit before approval.</small></span></summary>
    <div class="intake-source-actions">
      <a class="button-link" href="${url}" target="_blank" rel="noopener">View original</a>
      <a class="button-link secondary" href="${url}?download=true">Download</a>
      ${compact?'':`<button type="button" class="secondary" data-reanalyze-intake="${esc(id)}">Reanalyze and separate samples</button>`}
    </div>${viewer}</details>`
}

function intakeLabVintage(item,fields){
  for(const value of [fields?.vintage_year,fields?.annata,item?.extracted_data?.vintage_year,item?.extracted_data?.annata]){
    const year=Number(value)
    if(Number.isInteger(year)&&year>=1900&&year<=2100)return year
  }
  const match=JSON.stringify(item?.extracted_data||{}).match(/annata[^0-9]{0,24}(20\d{2})/i)
  return match?Number(match[1]):null
}

function intakeLabVarietyId(label){
  const wanted=String(label||'').trim().toLowerCase()
  return (state.reference?.varieties||[]).find(row=>{
    const name=String(row.name||'').trim().toLowerCase()
    return name===wanted||name.includes(wanted)||wanted.includes(name)
  })?.id||null
}

function normalizedIntakeSuggestions(item){
  const records=Array.isArray(item?.extracted_data?.suggested_database_records)?item.extracted_data.suggested_database_records:[]
  return records.flatMap(record=>{
    const type=intakeType(record.destination_section||record.section||record.record_type)
    const fields=record.fields||record.values||{}
    const results=Array.isArray(fields.results)?fields.results.filter(value=>value&&typeof value==='object'):[]
    if(type!=='lab'||results.length<2)return [record]
    const explicit=results.map(result=>String(result.sample_name||result.source_sample_label||result.variety_name||result.wine_type||'').trim())
    let labels=explicit
    if(!labels.every(Boolean)){
      const names=String(fields.sample_name||fields.source_sample_label||'').split(/\s*(?:\/|\+|,|;|\band\b|\be\b)\s*/i).map(value=>value.trim()).filter(Boolean)
      if(names.length===results.length)labels=names
    }
    if(!labels.every(Boolean)||new Set(labels.map(value=>value.toLowerCase())).size<2)return [record]
    const vintage=intakeLabVintage(item,fields)
    return results.map((result,index)=>{
      const sampleName=labels[index]
      return {...record,fields:{...fields,sample_name:sampleName,source_sample_label:sampleName,variety_id:intakeLabVarietyId(sampleName)||fields.variety_id||null,vintage_year:vintage||fields.vintage_year,results:[result]}}
    })
  })
}

function reportWorkflowLabel(type){
  if(type==='grape')return'Agronomy · pre-harvest'
  if(type==='must'||type==='wine')return'Enology · post-harvest'
  return'Laboratory · supporting evidence'
}

function completeLabReportItem(item){
  const candidates=[item,...(item?.related_items||[])].map(candidate=>{
    if(typeof candidate?.extracted_data==='string')try{candidate={...candidate,extracted_data:JSON.parse(candidate.extracted_data)} }catch{}
    return candidate
  })
  return candidates.find(candidate=>{
    const mime=String(candidate?.media_type||'').toLowerCase(),name=String(candidate?.original_filename||'').toLowerCase()
    return candidate?.classification==='lab_report'&&(mime==='application/pdf'||mime.startsWith('image/')||name.endsWith('.pdf'))&&normalizedIntakeSuggestions(candidate).some(record=>{
      const fields=record.fields||record.values||{}
      return String(fields.sample_name||fields.source_sample_label||'').trim()&&Array.isArray(fields.results)&&fields.results.length
    })
  })||null
}

function labReportApprovalSummary(report){
  const suggestions=normalizedIntakeSuggestions(report)
  const samples=suggestions.map((record,index)=>{
    const fields=record.fields||record.values||{},results=Array.isArray(fields.results)?fields.results:[]
    return `<div class="intake-report-sample"><span><b>${esc(fields.sample_name||fields.source_sample_label||`Sample ${index+1}`)}</b><small>${esc(reportWorkflowLabel(String(fields.sample_type||'other').toLowerCase()))} · ${esc(fields.lab_date||fields.report_date||'date needs review')}</small></span><strong>${results.length} result${results.length===1?'':'s'}</strong></div>`
  }).join('')
  const resultCount=suggestions.reduce((sum,record)=>sum+(((record.fields||record.values||{}).results)||[]).length,0)
  return `<section class="intake-report-approval"><header><div><b>Complete report recognized</b><small>Every listed sample and result will be saved from the original report in one reviewed action.</small></div><span>${suggestions.length} sample${suggestions.length===1?'':'s'} · ${resultCount} results</span></header>${samples}<button type="button" data-approve-lab-report="${esc(report.id)}">Approve full report</button><small>Only pre-harvest grape tests update harvest timing. Must and wine tests route to Enology.</small></section>`
}

const openIntakeReviewWithoutSource=openIntakeReview
openIntakeReview=async function(id){
  await openIntakeReviewWithoutSource(id)
  if(!$('intakeDialog')?.open)return
  try{
    const item=await api(`api/v1/intake/${id}`)
    state.intakeSource=item
    const report=completeLabReportItem(item)
    const reviewItem=report||item
    const reviewId=report?.id||id
    const suggestions=normalizedIntakeSuggestions(reviewItem)
    state.intakeDraft=suggestions
    $('intakeDetail')?.insertAdjacentHTML('afterbegin',intakeSourcePreview(reviewItem,reviewId))
    const linkedNames=new Set((reviewItem.linked_records||item.linked_records||[]).map(row=>String(row.sample_name||'').trim().toLowerCase()).filter(Boolean))
    const actions=$('intakeDetail')?.querySelector('.intake-actions')
    if(actions&&report){
      actions.innerHTML=labReportApprovalSummary(report)
      const approve=actions.querySelector('[data-approve-lab-report]')
      approve.onclick=async()=>{
        approve.disabled=true
        approve.textContent='Approving complete report…'
        try{
          const result=await api(`api/v1/intake/${encodeURIComponent(report.id)}/approve-lab-report`,{method:'POST',body:'{}'})
          $('intakeDialog').close()
          toast(`Approved ${result.sample_count} sample${result.sample_count===1?'':'s'} and ${result.result_count} results`)
          await loadAll()
        }catch(error){toast(error.message);approve.disabled=false;approve.textContent='Approve full report'}
      }
    }else if(actions&&item.classification==='lab_report'){
      actions.innerHTML=`<section class="intake-report-recovery"><div><b>The forwarded email arrived without its PDF.</b><small>The email text was retained, but it cannot create authoritative laboratory results. Attach the original PDF or a clear report image here; it will remain linked to this email.</small></div><label class="button-link secondary">Choose report<input type="file" data-intake-source-file accept=".pdf,application/pdf,image/*" hidden></label><button type="button" data-attach-intake-source disabled>Attach and analyze report</button><small data-intake-source-name>No report selected</small></section>`
      const picker=actions.querySelector('[data-intake-source-file]')
      const attach=actions.querySelector('[data-attach-intake-source]')
      const filename=actions.querySelector('[data-intake-source-name]')
      picker.onchange=()=>{
        const selected=picker.files?.[0]
        attach.disabled=!selected
        filename.textContent=selected?.name||'No report selected'
      }
      attach.onclick=async()=>{
        const selected=picker.files?.[0]
        if(!selected)return
        attach.disabled=true
        attach.textContent='Attaching and analyzing…'
        const form=new FormData()
        form.append('file',selected)
        try{
          const response=await fetch(`api/v1/intake/${encodeURIComponent(id)}/source-file`,{method:'POST',body:form})
          const payload=await response.json().catch(()=>({}))
          if(!response.ok)throw new Error(payload.detail||`Request failed (${response.status})`)
          $('intakeDialog').close()
          await loadAll()
          await openIntakeReview(payload.id)
          toast('Report attached and analyzed; review every sample before approval')
        }catch(error){
          toast(error.message)
          attach.disabled=false
          attach.textContent='Attach and analyze report'
        }
      }
    }else if(actions&&suggestions.length)actions.innerHTML=suggestions.map((record,index)=>`<button type="button" data-use-intake="${index}">Review proposed record ${index+1}</button>`).join('')
    if(report)return
    ;suggestions.forEach((record,index)=>{
      const button=actions?.querySelector(`[data-use-intake="${index}"]`)
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

document.addEventListener('click',event=>{
  const button=event.target.closest('#intakeDialog [data-use-intake]')
  if(!button||button.disabled||button.dataset.reviewHandled==='1'||typeof button.onclick==='function')return
  const index=Number(button.dataset.useIntake),record=(state.intakeDraft||[])[index]
  if(!record)return
  button.dataset.reviewHandled='1'
  const fields=record.fields||record.values||{}
  $('intakeDialog')?.close()
  openEntry(intakeType(record.destination_section||record.section||record.record_type),fields,state.intakeItemId)
})

const openEntryWithoutIntakeSource=openEntry
openEntry=function(type,draft=null,intakeId=null){
  openEntryWithoutIntakeSource(type,draft,intakeId)
  if(intakeId&&state.intakeSource)$('formFields')?.insertAdjacentHTML('afterbegin',intakeSourcePreview(state.intakeSource,intakeId,true))
}
