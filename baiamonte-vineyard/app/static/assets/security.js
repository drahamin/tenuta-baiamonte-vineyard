/* Administrator-only estate vehicle security workspace. */
let securityWorkspace=null;

const securityVehicleName=row=>row.tag_label||row.staff_name||row.display_name||[row.vehicle_color,row.vehicle_make,row.vehicle_model,row.vehicle_type].filter(Boolean).join(' ')||'Unidentified vehicle';
const securityDateValue=()=>$('securityDay')?.value||new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Rome'});
const securityMetric=(label,value,note='')=>`<article><small>${esc(label)}</small><strong>${esc(value)}</strong>${note?`<span>${esc(note)}</span>`:''}</article>`;

function renderSecurityWorkspace(data){
  securityWorkspace=data;
  if($('securityDay')&&!$('securityDay').value)$('securityDay').value=data.day;
  if($('securityPolicy'))$('securityPolicy').textContent=data.policy;
  const summary=data.summary||{};
  $('securityPrimaryKpis').innerHTML=[
    securityMetric('Needs review',summary.needs_review||0,summary.needs_review?'admin decisions waiting':'queue clear'),
    securityMetric('Entries / exits',`${summary.entries||0} / ${summary.exits||0}`,'selected day'),
    securityMetric('Vehicles observed',summary.vehicles||0,'all camera findings'),
    securityMetric('Flagged',summary.flagged||0,summary.flagged?'check today':'none today')
  ].join('');
  $('securityKpis').innerHTML=[
    securityMetric('Staff matches',summary.known_staff||0,'advisory'),securityMetric('Readable plates',summary.plates||0,'genuinely legible'),
    securityMetric('Known vehicles',summary.known_vehicles||0,`${summary.known_observations||0} sightings`),securityMetric('Evidence cameras',(data.cameras||[]).filter(row=>row.enabled).length,'enabled')
  ].join('');
  $('securityStatusLights').innerHTML=`<span class="${(data.cameras||[]).some(row=>row.enabled)?'ok':'warning'}"><i></i><b>${(data.cameras||[]).filter(row=>row.enabled).length} cameras</b><small>selected</small></span><span class="${summary.needs_review?'warning':'ok'}"><i></i><b>${summary.needs_review||0} reviews</b><small>${summary.needs_review?'attention':'clear'}</small></span><span class="${summary.known_flagged?'warning':'ok'}"><i></i><b>${summary.known_flagged||0} known flags</b><small>registry</small></span>`;
  renderSecurityMovements(data.movements||[]);
  renderSecurityReviewQueue(data.movements||[]);
  renderKnownVehicles(data.known_vehicles||[],summary);
  renderSecurityCameras(data.cameras||[],data.camera_catalog||[]);
}

function securityMovementMarkup(row){return `<article class="security-movement ${row.flagged?'flagged':''} ${row.review_status==='rejected'?'rejected':''}">
    <div class="security-movement-icon">${row.movement_state==='entry'?'→':row.movement_state==='exit'?'←':row.movement_state==='parked'?'P':'•'}</div>
    <div><header><b>${esc(securityVehicleName(row))}</b><span>${esc(row.movement_state||'unknown')}</span>${row.flagged?'<em>FLAGGED</em>':''}</header><p>${esc(row.camera_name||row.camera_entity_id)} · ${esc(row.observation_zone||'estate')} · ${row.observed_at?esc(timeLabel(row.observed_at)):'—'}</p><small>${row.license_plate?`Plate ${esc(row.license_plate)} · `:''}${esc(row.subject_category||'unknown')} · ${Math.round(Number(row.confidence_pct||0))}% confidence · ${esc(row.review_status||'unreviewed')}</small></div>
    <div class="security-movement-actions">${row.evidence_id?`<button type="button" class="secondary" data-security-frame="${esc(row.evidence_id)}">View frame</button>`:''}<button type="button" data-security-review="${esc(row.id)}">Review / tag</button></div>
  </article>`}

function bindSecurityMovements(list){
  list.querySelectorAll('[data-security-frame]').forEach(button=>button.onclick=()=>viewRetainedCameraEvidence(button.dataset.securityFrame,button));
  list.querySelectorAll('[data-security-review]').forEach(button=>button.onclick=()=>openSecurityReview(button.dataset.securityReview));
}

function renderSecurityMovements(rows){
  const list=$('securityMovementList');
  if(!rows.length){list.className='security-movement-list empty';list.textContent='No vehicle observations for this day.';return}
  list.className='security-movement-list';
  list.innerHTML=rows.map(securityMovementMarkup).join('');bindSecurityMovements(list);
}

function renderSecurityReviewQueue(rows){
  const reviewRows=rows.filter(row=>!['confirmed','rejected'].includes(String(row.review_status||'').toLowerCase())),list=$('securityReviewList');
  $('securityReviewCount').textContent=`${reviewRows.length} open`;
  if(!reviewRows.length){list.className='security-movement-list empty security-clear-state';list.innerHTML='<b>Review queue clear</b><span>New vehicle findings will appear here before they teach the known-car registry.</span>';return}
  list.className='security-movement-list security-review-list';list.innerHTML=reviewRows.map(securityMovementMarkup).join('');bindSecurityMovements(list);
}

function renderKnownVehicles(rows,summary){
  $('securityKnownStats').innerHTML=[securityMetric('Known',rows.length),securityMetric('Confirmed sightings',summary.known_observations||0),securityMetric('Staff-linked',rows.filter(row=>row.person_entity).length),securityMetric('Flagged',rows.filter(row=>row.flagged).length)].join('');
  const list=$('securityKnownVehicles');
  if(!rows.length){list.className='security-known-list empty';list.textContent='Confirm and tag an observation to begin the known-car database.';return}
  list.className='security-known-list';
  list.innerHTML=rows.map(row=>`<div class="security-known-vehicle ${row.flagged?'flagged':''}"><div><b>${esc(securityVehicleName(row))}</b><small>${esc([row.vehicle_color,row.vehicle_make,row.vehicle_model,row.license_plate].filter(Boolean).join(' · ')||'Appearance retained from reviewed evidence')}</small><span>${esc(row.subject_category||'unknown')} · ${Number(row.confirmed_observations||0)} confirmed · last ${row.last_seen_at?esc(timeLabel(row.last_seen_at)):'—'}</span>${row.flag_reason?`<em>${esc(row.flag_reason)}</em>`:''}</div><button type="button" class="secondary" data-archive-known="${esc(row.id)}">Archive</button></div>`).join('');
  list.querySelectorAll('[data-archive-known]').forEach(button=>button.onclick=async()=>{if(!confirm('Archive this known-car record? Earlier evidence remains in the audit ledger.'))return;button.disabled=true;try{await api(`api/v1/admin/security/known-vehicles/${encodeURIComponent(button.dataset.archiveKnown)}`,{method:'DELETE'});toast('Known car archived');await loadSecurityWorkspace()}catch(error){toast(error.message)}finally{button.disabled=false}});
}

function securityCameraRow(row,catalog){
  const selected=row.camera_entity_id||'';
  const options=[...catalog];if(selected&&!options.some(item=>item.entity_id===selected))options.push({entity_id:selected,name:row.display_name||selected});
  return `<div class="security-camera-row"><label>Camera<select name="camera_entity_id">${options.map(item=>`<option value="${esc(item.entity_id)}" ${item.entity_id===selected?'selected':''}>${esc(item.name||item.entity_id)}</option>`).join('')}</select></label><label>Name<input name="display_name" value="${esc(row.display_name||'')}"></label><label>Role<select name="source_role">${[['entry_exit','Entry / exit'],['parking','Parking'],['doorbell','Doorbell'],['perimeter','Perimeter'],['supporting','Supporting']].map(([value,label])=>`<option value="${value}" ${row.source_role===value?'selected':''}>${label}</option>`).join('')}</select></label><label>Direction<select name="direction_rule">${[['none','No direction rule'],['front_right_entry','Vehicle front right = entry'],['front_left_entry','Vehicle front left = entry'],['toward_entry','Toward camera = entry'],['away_entry','Away from camera = entry']].map(([value,label])=>`<option value="${value}" ${row.direction_rule===value?'selected':''}>${label}</option>`).join('')}</select></label><label class="security-camera-check"><input type="checkbox" name="enabled" ${row.enabled==null||Boolean(row.enabled)?'checked':''}>Enabled</label><label class="security-camera-check"><input type="checkbox" name="always_analyze" ${row.always_analyze?'checked':''}>Always analyze</label><button type="button" class="danger" data-remove-security-camera>Remove</button></div>`;
}

function renderSecurityCameras(rows,catalog){
  const list=$('securityCameraList');list.dataset.catalog=JSON.stringify(catalog);list.innerHTML=rows.map(row=>securityCameraRow(row,catalog)).join('');bindSecurityCameraRows();
}
function bindSecurityCameraRows(){$('securityCameraList')?.querySelectorAll('[data-remove-security-camera]').forEach(button=>button.onclick=()=>button.closest('.security-camera-row').remove())}

function openSecurityReview(id){
  const row=(securityWorkspace?.movements||[]).find(item=>item.id===id);if(!row)return;
  const form=$('securityMovementForm');form.reset();form.elements.id.value=row.id;form.elements.movement_state.value=row.movement_state||'unknown';form.elements.license_plate.value=row.license_plate||'';form.elements.subject_category.value=row.subject_category||'unknown';form.elements.tag_label.value=row.tag_label||row.staff_name||'';form.elements.flagged.checked=Boolean(row.flagged);form.elements.flag_reason.value=row.flag_reason||'';form.elements.review_status.value=row.review_status==='rejected'?'rejected':'confirmed';form.elements.review_notes.value=row.review_notes||'';
  form.elements.staff_person_entity.innerHTML='<option value="">Not linked</option>'+((securityWorkspace?.staff)||[]).map(person=>`<option value="${esc(person.person_entity)}">${esc(person.name)}</option>`).join('');form.elements.staff_person_entity.value=row.staff_person_entity||'';
  $('securityMovementTitle').textContent=securityVehicleName(row);$('securityMovementDialog').showModal();
}

async function loadSecurityWorkspace(){
  if(!$('view-admin-security')||!state.session?.permissions?.admin)return;
  try{const data=await api(`api/v1/admin/security/dashboard?day=${encodeURIComponent(securityDateValue())}`);renderSecurityWorkspace(data)}catch(error){$('securityMovementList').className='security-movement-list empty';$('securityMovementList').textContent=error.message}
}

if($('securityDay'))$('securityDay').value=new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Rome'});
$('securityRefresh')?.addEventListener('click',loadSecurityWorkspace);
$('securityDay')?.addEventListener('change',loadSecurityWorkspace);
$('securityScan')?.addEventListener('click',async event=>{event.currentTarget.disabled=true;try{const result=await api('api/v1/admin/security/scan',{method:'POST'});toast(result.movements?`${result.movements} vehicle finding${result.movements===1?'':'s'} added`:result.reason||'Camera checked');await loadSecurityWorkspace()}catch(error){toast(error.message)}finally{event.currentTarget.disabled=false}});
$('securityAddCamera')?.addEventListener('click',()=>{const list=$('securityCameraList'),catalog=JSON.parse(list.dataset.catalog||'[]');if(!catalog.length){toast('No Home Assistant cameras are currently available');return}list.insertAdjacentHTML('beforeend',securityCameraRow({enabled:true,source_role:'supporting',direction_rule:'none'},catalog));bindSecurityCameraRows()});
$('securityCameraForm')?.addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter,rows=[...$('securityCameraList').querySelectorAll('.security-camera-row')].map(node=>{const get=name=>node.querySelector(`[name="${name}"]`);return{camera_entity_id:get('camera_entity_id').value,display_name:get('display_name').value,source_role:get('source_role').value,direction_rule:get('direction_rule').value,enabled:get('enabled').checked,always_analyze:get('always_analyze').checked}});button.disabled=true;try{await api('api/v1/admin/security/cameras',{method:'PUT',body:JSON.stringify({cameras:rows})});toast('Security camera pipeline saved');await loadSecurityWorkspace()}catch(error){toast(error.message)}finally{button.disabled=false}});
$('securityMovementForm')?.addEventListener('submit',async event=>{event.preventDefault();const form=new FormData(event.currentTarget),button=event.submitter,payload={movement_state:form.get('movement_state'),license_plate:form.get('license_plate'),subject_category:form.get('subject_category'),staff_person_entity:form.get('staff_person_entity'),tag_label:form.get('tag_label'),flagged:form.get('flagged')==='on',flag_reason:form.get('flag_reason'),review_status:form.get('review_status'),review_notes:form.get('review_notes')};button.disabled=true;try{await api(`api/v1/admin/security/movements/${encodeURIComponent(form.get('id'))}`,{method:'PATCH',body:JSON.stringify(payload)});$('securityMovementDialog').close();toast(payload.review_status==='confirmed'?'Observation confirmed; known-car learning updated':'Review saved');await loadSecurityWorkspace()}catch(error){toast(error.message)}finally{button.disabled=false}});

window.loadSecurityWorkspace=loadSecurityWorkspace;
