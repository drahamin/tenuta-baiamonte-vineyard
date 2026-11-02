let payrollReviewPeriod=null;
function payrollReviewProjection(data,period=payrollReviewPeriod){
  const workers=data.worker_submissions||[],approved=workers.filter(row=>row.approval_status==='approved'&&(!row.payment_status||['unpaid','unknown','part_paid'].includes(row.payment_status))),approvedIds=new Set(workers.filter(row=>row.approval_status==='approved').map(row=>String(row.id)));
  const owners=(data.owner_labor_reviews||[]).filter(row=>(!row.approval_status||row.approval_status==='draft')&&!approvedIds.has(String(row.id))),pending=workers.filter(row=>['submitted','rejected'].includes(row.approval_status));
  const month=row=>/^\d{4}-(0[1-9]|1[0-2])-\d{2}/.test(String(row.work_date||''))?String(row.work_date).slice(0,7):'unknown';
  const periods=[...new Set([...owners,...pending].map(month))].sort().reverse();
  if(period==null||(period!=='all'&&!periods.includes(period)))period=owners.map(month).filter(value=>value!=='unknown').sort().reverse()[0]||'all';
  const selected=row=>period==='all'||month(row)===period,ownerRows=owners.filter(selected),workerRows=pending.filter(selected);
  return {period,periods,ownerRows,workerRows,reviewCount:ownerRows.length+workerRows.length,approvedRows:approved};
}
function payrollReviewPeriodLabel(period){return period==='all'?'All review periods':period==='unknown'?'Unknown work month':new Date(`${period}-01T12:00:00Z`).toLocaleDateString('en',{year:'numeric',month:'long',timeZone:'UTC'})}
function renderPayrollReviewPeriod(data){
  const projection=payrollReviewProjection(data);payrollReviewPeriod=projection.period;
  const node=document.getElementById('adminLaborReviewPeriodControl');if(!node)return projection;
  node.innerHTML=`<label>Review period<select id="adminLaborReviewPeriod"><option value="all">All review periods</option>${projection.periods.map(period=>`<option value="${esc(period)}">${esc(payrollReviewPeriodLabel(period))}</option>`).join('')}</select></label><p>${projection.reviewCount} labor records awaiting review — ${projection.ownerRows.length} owner drafts + ${projection.workerRows.length} worker submissions. Not payable until separately approved. Approved payments and totals below remain all-period.</p>`;
  const select=node.querySelector('select');select.value=projection.period;select.onchange=()=>{payrollReviewPeriod=select.value;renderAdminControl()};return projection;
}
function ownerLaborReviewCard(row,revision=''){
  const exact=value=>esc(String(value));
  if([row.other_cost_eur,row.expense_amount_eur].some(value=>value!=null&&(!Number.isFinite(Number(value))||Number(value)!==0)))return `<article class="worker-admin-review" data-owner-labor="${esc(row.id)}"><div><b>${esc(row.person_or_crew)}</b><p>Additional expenses require separate reconciliation. This wages-only approval is unavailable.</p><small>Source: ${esc(row.source_labor_id||'')}</small><output data-owner-result></output></div></article>`;
  const source=String(row.source_labor_id||''),monthly=source.endsWith('-GIANCARLO')||source.endsWith('-VINCENZO-PART-TIME'),known=[row.regular_hours,row.hourly_rate_eur,row.labor_cost_eur].every(value=>value!=null&&Number.isFinite(Number(value))&&Number(value)>0)&&[row.other_cost_eur,row.expense_amount_eur].every(value=>value==null||(Number.isFinite(Number(value))&&Number(value)===0)),period=monthly?`October 2026 month total · ${row.work_date||'no anchor'} is a month anchor`:`Actual shift date · ${row.work_date||'unknown'}`;
  return `<article class="worker-admin-review" data-owner-labor="${esc(row.id)}"><div><b>${esc(row.person_or_crew)}</b><small>${esc(period)}</small><p>${row.regular_hours==null?'Unknown':exact(row.regular_hours)} regular hours · overtime ${row.overtime_hours==null?'unknown':`${exact(row.overtime_hours)} h`}</p><p>${row.hourly_rate_eur==null?'Rate unknown':`€${exact(row.hourly_rate_eur)} / h`} · ${row.labor_cost_eur==null?'Validated wages unknown':`€${exact(row.labor_cost_eur)} known wages`}</p><small>Other costs: ${row.other_cost_eur==null?'unknown':`€${exact(row.other_cost_eur)}`} · Due date: ${esc(row.pay_due_date||'not recorded')}</small><p>${esc(row.work_performed||'')}</p><p>${esc(row.notes||'')}</p><small>Source: ${esc(source)}</small>${known?`<button type="button" class="secondary" data-owner-load>Load current review</button>${revision?`<label><input type="checkbox" data-owner-verified> I checked the source and verified these known wages.</label><label>Review note<textarea data-owner-note></textarea></label><button type="button" data-owner-approve disabled>Approve wages into unpaid queue</button>`:''}`:'<em>Awaiting normal payroll worksheet review. Validated amount and rate are unknown; approval is unavailable.</em>'}<output data-owner-result></output></div></article>`;
}
function ownerApprovalCommandId(){
  if(crypto.randomUUID)return crypto.randomUUID();
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
function bindOwnerLaborReview(card,row,revision=''){
  const load=card.querySelector('[data-owner-load]');
  if(load)load.onclick=async()=>{load.disabled=true;try{const review=await api(`api/v1/admin/owner-labor/${encodeURIComponent(row.id)}/review`);card.outerHTML=ownerLaborReviewCard(review.record,review.review_revision);const fresh=[...document.querySelectorAll('[data-owner-labor]')].find(node=>node.dataset.ownerLabor===String(row.id));if(fresh)bindOwnerLaborReview(fresh,review.record,review.review_revision)}catch(error){card.querySelector('[data-owner-result]').textContent=error.message;load.disabled=false}};
  const approve=card.querySelector('[data-owner-approve]');if(!approve)return;
  const checked=card.querySelector('[data-owner-verified]'),note=card.querySelector('[data-owner-note]');let command=null;
  const update=()=>{approve.disabled=!checked.checked||!note.value.trim()};checked.onchange=update;note.oninput=update;
  approve.onclick=async()=>{if(!command){if(!checked.checked||!note.value.trim())return;command={command_id:ownerApprovalCommandId(),review_revision:revision,verified_wages:true,review_note:note.value.trim()}}approve.disabled=true;checked.disabled=true;note.readOnly=true;try{const result=await api(`api/v1/admin/owner-labor/${encodeURIComponent(row.id)}/approve`,{method:'POST',body:JSON.stringify(command)});card.querySelector('[data-owner-result]').textContent=`Approved into unpaid queue · ${result.command_id} · ${result.command_timestamp}`;await loadAdminControl()}catch(error){card.querySelector('[data-owner-result]').textContent=error.message;approve.textContent='Retry same approval command';approve.disabled=false}};
}
function renderOwnerLaborReviews(data){
  const projection=renderPayrollReviewPeriod(data);
  document.getElementById('adminOwnerLaborReviews')?.remove();const anchor=document.getElementById('adminTimesheetReviews'),rows=projection.ownerRows;if(!anchor||!(data.owner_labor_reviews||[]).length)return;
  anchor.insertAdjacentHTML('beforebegin',`<section id="adminOwnerLaborReviews"><h3>Owner reconciliation · ${esc(payrollReviewPeriodLabel(projection.period))}</h3><p>${rows.length} owner drafts awaiting review. Approval adds verified wages to the unpaid queue; it does not pay them.</p>${rows.map(row=>ownerLaborReviewCard(row)).join('')||'<p>No owner drafts in this review period.</p>'}</section>`);
  document.getElementById('adminOwnerLaborReviews').querySelectorAll('[data-owner-labor]').forEach(card=>bindOwnerLaborReview(card,rows.find(row=>String(row.id)===card.dataset.ownerLabor)));
}
