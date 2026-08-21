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

const openIntakeReviewWithoutSource=openIntakeReview
openIntakeReview=async function(id){
  await openIntakeReviewWithoutSource(id)
  if(!$('intakeDialog')?.open)return
  try{
    const item=await api(`api/v1/intake/${id}`)
    state.intakeSource=item
    const suggestions=normalizedIntakeSuggestions(item)
    state.intakeDraft=suggestions
    $('intakeDetail')?.insertAdjacentHTML('afterbegin',intakeSourcePreview(item,id))
    const linkedNames=new Set((item.linked_records||[]).map(row=>String(row.sample_name||'').trim().toLowerCase()).filter(Boolean))
    const actions=$('intakeDetail')?.querySelector('.intake-actions')
    if(actions&&suggestions.length)actions.innerHTML=suggestions.map((record,index)=>`<button type="button" data-use-intake="${index}">Review proposed record ${index+1}</button>`).join('')
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
