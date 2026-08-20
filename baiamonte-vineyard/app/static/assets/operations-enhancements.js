/* Cross-dashboard presentation kept separate from the main application bundle. */
(function () {
  const money = value => new Intl.NumberFormat(undefined, {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(Number(value || 0));
  const number = value => new Intl.NumberFormat(undefined, {maximumFractionDigits: 1}).format(Number(value || 0));
  const metrics = payroll => `
    <article class="metric"><span>Approved hours</span><strong>${number(payroll?.approved_hours_ytd)} h</strong><small>${payroll?.year || ''} year to date</small></article>
    <article class="metric"><span>Labor cost</span><strong>${money(payroll?.labor_cost_ytd)}</strong><small>approved this year</small></article>
    <article class="metric"><span>Reimbursements</span><strong>${money(payroll?.reimbursements_ytd)}</strong><small>approved this year</small></article>
    <article class="metric"><span>Ready to pay</span><strong>${money(payroll?.ready_to_pay)}</strong><small>${Number(payroll?.payment_items || 0)} queued records</small></article>
    <article class="metric"><span>Awaiting review</span><strong>${Number(payroll?.awaiting_review || 0)}</strong><small>not yet approved</small></article>
    <article class="metric"><span>Paid</span><strong>${money(payroll?.paid_ytd)}</strong><small>${payroll?.year || ''} year to date</small></article>`;

  const originalFinance = window.renderFinance;
  window.renderFinance = function () {
    originalFinance?.();
    const node = document.getElementById('financePayrollSummary');
    if (node) node.innerHTML = metrics(state?.finance?.payroll || {});
  };

  const originalAdminControl = window.renderAdminControl;
  window.renderAdminControl = function () {
    originalAdminControl?.();
    const node = document.getElementById('adminControlPayroll');
    if (node) node.innerHTML = metrics(state?.adminControl?.payroll || {});
  };

  const originalSocial = window.renderSocial;
  window.renderSocial = function () {
    originalSocial?.();
    const data = state?.social || {};
    [['facebook', data.facebook], ['instagram', data.instagram]].forEach(([name, channel]) => {
      if (!channel?.publishing_ready || channel.connected) return;
      const light = document.querySelector(`#socialLights .system-light:nth-child(${name === 'facebook' ? 1 : 2})`);
      light?.classList.remove('red', 'amber');
      light?.classList.add('green');
      const label = light?.querySelector('small');
      if (label) label.textContent = 'Publishing ready';
      const diagnostic = document.getElementById(`${name}Diagnostic`);
      if (diagnostic) {
        diagnostic.className = 'social-diagnostic good';
        const readbackError = channel.error ? ` ${esc(String(channel.error).slice(0, 180))}` : '';
        diagnostic.innerHTML = `<b>Publishing ready</b><span>Posting works; recent-post readback is currently limited.${readbackError}</span>`;
      }
    });
  };
}());

const renderEtnaOperationalBase=renderEtna;
renderEtna=function(){
  renderEtnaOperationalBase();
  const events=state.etna?.seismic_events||[],romeDay=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Rome',year:'numeric',month:'2-digit',day:'2-digit'}),todayRome=romeDay.format(new Date()),quake=events.find(row=>Number(row.magnitude)>=3&&row.time&&romeDay.format(new Date(row.time))===todayRome),activity=state.etna?.activity||{},hero=$('etnaHero'),ticker=$('etnaTicker');
  if(!hero||!ticker)return;
  const appendFreshness=()=>{
    const payload=state.etna||{},detail=$('etnaStateDetail'),stale=payload.stale_sources||Object.keys(payload.errors||{});
    if(payload.fresh!==false||!detail)return;
    const attempted=payload.generated_at?new Date(payload.generated_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'recently',complete=payload.last_complete_at?` · last complete ${new Date(payload.last_complete_at).toLocaleString()}`:'';
    detail.textContent+=` · PARTIAL UPDATE ${attempted}: cached ${stale.length?stale.join(', '):'source data'}${complete}`;
  };
  hero.classList.toggle('seismic-alert',Boolean(quake));
  ticker.hidden=!quake&&!activity.active;
  if(!quake){if(activity.active)ticker.querySelector('span').textContent=`ETNA ACTIVITY ALERT · ${activity.label||'Official INGV notice'} · Follow Civil Protection and INGV guidance · `.repeat(2);appendFreshness();return;}
  const magnitude=Number(quake.magnitude).toFixed(1),text=`SEISMIC ALERT · M${magnitude} · ${quake.place||'Etna area'} · Check estate, cellar and utilities · `;
  if(!activity.active){$('etnaState').textContent=`Nearby earthquake · M${magnitude}`;$('etnaStateDetail').textContent=`${quake.place||'Etna area'} · ${new Date(quake.time).toLocaleString()} · inspect the estate, cellar and utilities.`;}
  ticker.querySelector('span').textContent=text.repeat(2);
  appendFreshness();
};

// Finance values stay private even though the operating-history view is shared.
// Treatment trends represent completed work; planned rows remain visible only as context.
renderHistory=function(){
  const rows=state.history||[],node=$('historyTable');
  if(!node)return;
  const canFinance=Boolean(state.session?.permissions?.finance),financeMeasures=new Set(['expenses_eur','payments_eur']),select=$('historyMeasure');
  if(!canFinance&&financeMeasures.has(select?.value))select.value='harvest_kg';
  const visible=rows.filter(row=>Object.entries(row).some(([key,value])=>key!=='year'&&!financeMeasures.has(key)&&numeric(value)>0));
  node.innerHTML=visible.length?`<div class="trend-head history-head"><b>Year</b><b>Grapes</b><b>Cellar</b><b>Labor / work</b><b>Other</b></div>${visible.map(row=>{
    const workRecords=Number(row.historical_work_records||0),dateParts=[row.historical_exact_date_records?`${row.historical_exact_date_records} exact`:null,row.historical_month_date_records?`${row.historical_month_date_records} month`:null,row.historical_broad_date_records?`${row.historical_broad_date_records} broad`:null].filter(Boolean).join(' · '),laborText=row.labor_hours==null?(workRecords?'Hours not recorded':'Unknown'):`${fmt(row.labor_hours)} h${row.labor_hours_status==='partial'?' known':''}`,completed=Number(row.treatments_completed??row.treatments??0),treatmentRecords=Number(row.treatment_records??completed),otherTreatments=Math.max(0,treatmentRecords-completed),financeText=canFinance?`<br><small>${row.expenses_eur==null?'No cost history':eur(row.expenses_eur)+' expenses'}${row.payments_eur==null?'':' · '+eur(row.payments_eur)+' payments'} · ${known(row.olives_kg,' kg olives')} · ${known(row.oil_l,' L oil')}</small>`:`<br><small>${known(row.olives_kg,' kg olives')} · ${known(row.oil_l,' L oil')}</small>`;
    return`<div class="trend-row history-row-data"><b>${row.year}</b><span>${known(row.harvest_kg,' kg')}<br><small>${row.harvest_lots||0} lots</small></span><span>${known(row.cellar_l,' L')}</span><span>${laborText}<br><small>${workRecords?`${workRecords} source records${dateParts?' · '+dateParts:''}`:row.labor_entries?`${row.labor_entries} labor entries`:'No work history'}</small></span><span>${completed} completed treatment${completed===1?'':'s'}${otherTreatments?` · ${otherTreatments} planned/other`:''} · ${row.lab_samples||0} labs${financeText}</span></div>`;
  }).join('')}`:'No multi-year operating records yet.';
  const ordered=visible.filter(row=>Number(row.year)>=firstEstateVintage).sort((a,b)=>a.year-b.year),measure=select?.value||'harvest_kg',valueForChart=row=>{
    if(Number(row.year)!==estateYear)return numeric(row[measure]);
    if(measure==='harvest_kg'&&!Number(row.harvest_lots||0))return null;
    if(measure==='treatments'&&!Number(row.treatment_records||0))return null;
    if(measure==='lab_samples'&&!Number(row.lab_samples||0))return null;
    return numeric(row[measure]);
  };
  const values=ordered.map(valueForChart),firstRecorded=values.findIndex(value=>value!==null),lastKnown=values.reduce((last,value,index)=>value!==null?index:last,-1),lastRecorded=Math.max(lastKnown,ordered.findIndex(row=>Number(row.year)===estateYear)),chartRows=firstRecorded<0?[]:ordered.slice(firstRecorded,lastRecorded+1),chartValues=firstRecorded<0?[]:values.slice(firstRecorded,lastRecorded+1);
  lineChart('historyChart',[{name:measure,zeroBased:true,values:chartValues}],['#c5a35f'],260,chartRows.map(row=>String(row.year)));
};
if($('historyMeasure'))$('historyMeasure').onchange=renderHistory;

async function saveOliveHarvestPreference(event){
  event.preventDefault();
  const button=event.submitter,payload=Object.fromEntries(new FormData(event.currentTarget).entries());
  button.disabled=true;
  try{
    await api(`api/v1/olives/harvest-preference/${state.year}`,{method:'PUT',body:JSON.stringify(payload)});
    state.olives=await api(`api/v1/olives/dashboard?year=${state.year}`);
    renderOlives();
    renderTodayOlives();
    toast('Olive harvest strategy saved and prediction updated');
  }catch(error){toast(error.message)}finally{button.disabled=false}
}
if($('oliveHarvestPreferenceForm'))$('oliveHarvestPreferenceForm').onsubmit=saveOliveHarvestPreference;

function renderTodayOlives(){
  const panel=$('todayOlivePanel');
  if(!panel)return;
  const olives=state.olives;
  if(!olives){
    $('todayOliveStrategy').textContent='Unavailable';
    $('todayOliveStrategyDetail').textContent='The olive dashboard did not load';
    $('todayOliveDate').textContent='—';$('todayOliveWindow').textContent='—';$('todayOliveSeason').textContent='—';
    $('todayOliveConfidence').textContent='No forecast evidence';$('todayOliveSeasonDetail').textContent='No records loaded';
    $('todayOliveGuidance').textContent='Open the Olives page after the data connection is restored.';
    return;
  }
  const preference=olives.harvest_preference||{},forecast=olives.harvest_forecast||{},metrics=olives.metrics||{},treatments=olives.treatments||[],records=olives.records||[],models=olives.harvest_style_models||[],model=models.find(item=>item.code===preference.style_code),formatDate=value=>value?new Date(`${String(value).slice(0,10)}T12:00:00`).toLocaleDateString(undefined,{month:'short',day:'numeric'}):'—';
  $('todayOliveStrategy').textContent=forecast.style_name||model?.name||'Not selected';
  $('todayOliveStrategyDetail').textContent=preference.saved?'Saved owner strategy':'Suggested strategy · save on Olives';
  $('todayOliveDate').textContent=formatDate(forecast.estimated_date);
  $('todayOliveConfidence').textContent=forecast.status==='recorded'?'Recorded actual':`${forecast.confidence||'Unknown'} confidence · ${Number(forecast.training_samples||0)} exact prior harvest${Number(forecast.training_samples||0)===1?'':'s'}`;
  $('todayOliveWindow').textContent=forecast.window_start&&forecast.window_end?`${formatDate(forecast.window_start)}–${formatDate(forecast.window_end)}`:'Not available';
  $('todayOliveSeason').textContent=metrics.olives_kg==null?'No harvest yet':`${fmt(metrics.olives_kg)} kg`;
  $('todayOliveSeasonDetail').textContent=`${records.length} olive record${records.length===1?'':'s'} · ${treatments.length} treatment${treatments.length===1?'':'s'}`;
  $('todayOliveGuidance').textContent=forecast.guardrail||'Confirm representative fruit maturity, healthy fruit, dry picking weather and same-day mill capacity before harvesting.';
}

function renderTodayContext(){
  const now=new Date(),romeYear=Number(new Intl.DateTimeFormat('en',{timeZone:'Europe/Rome',year:'numeric'}).format(now)),historical=Number(state.year)!==romeYear;
  if($('todayDate'))$('todayDate').textContent=new Intl.DateTimeFormat(undefined,{timeZone:'Europe/Rome',weekday:'long',month:'long',day:'numeric'}).format(now);
  if($('heroNote'))$('heroNote').textContent=historical?`${state.year} vintage review · estate systems below remain live`:`Live estate conditions · ${state.year} vintage`;
}

const todayScrollState=new Map();
let todayScrollFrame=0,todayScrollLast=0;
function refreshTodayAutoScroll(){
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const todayActive=document.querySelector('#view-today.active');
  let hasOverflow=false;
  document.querySelectorAll('#view-today .list').forEach(node=>{
    let item=todayScrollState.get(node);
    if(!item){
      item={direction:1,pausedUntil:0};
      todayScrollState.set(node,item);
      node.addEventListener('mouseenter',()=>{item.pausedUntil=Infinity});
      node.addEventListener('mouseleave',()=>{item.pausedUntil=performance.now()+1200});
      node.addEventListener('focusin',()=>{item.pausedUntil=Infinity});
      node.addEventListener('focusout',()=>{item.pausedUntil=performance.now()+1600});
      node.addEventListener('touchstart',()=>{item.pausedUntil=Infinity},{passive:true});
      node.addEventListener('touchend',()=>{item.pausedUntil=performance.now()+5000},{passive:true});
    }
    const overflowing=!reduced&&node.scrollHeight>node.clientHeight+2;
    hasOverflow=hasOverflow||overflowing;
    node.classList.toggle('today-auto-scroll',overflowing);
    if(!overflowing){node.classList.remove('at-scroll-end');item.direction=1}
  });
  if(todayScrollFrame&&(!todayActive||!hasOverflow)){cancelAnimationFrame(todayScrollFrame);todayScrollFrame=0;todayScrollLast=0}
  if(!todayScrollFrame&&todayActive&&hasOverflow)todayScrollFrame=requestAnimationFrame(stepTodayAutoScroll);
}
function stepTodayAutoScroll(now){
  const elapsed=Math.min(50,Math.max(0,now-(todayScrollLast||now)));
  todayScrollLast=now;
  const todayActive=document.querySelector('#view-today.active');
  let hasScrollableList=false;
  todayScrollState.forEach((item,node)=>{
    if(!todayActive||!node.classList.contains('today-auto-scroll'))return;
    hasScrollableList=true;
    if(now<item.pausedUntil)return;
    const bottom=Math.max(0,node.scrollHeight-node.clientHeight);
    node.scrollTop+=item.direction*elapsed*.012;
    if(node.scrollTop>=bottom-1){node.scrollTop=bottom;item.direction=-1;item.pausedUntil=now+1800;node.classList.add('at-scroll-end')}
    else if(node.scrollTop<=1&&item.direction<0){node.scrollTop=0;item.direction=1;item.pausedUntil=now+1800;node.classList.remove('at-scroll-end')}
  });
  if(todayActive&&hasScrollableList)todayScrollFrame=requestAnimationFrame(stepTodayAutoScroll);
  else{todayScrollFrame=0;todayScrollLast=0}
}

const renderWithTodayOlives=render;
render=function(){renderWithTodayOlives();renderTodayOlives();renderTodayContext();requestAnimationFrame(refreshTodayAutoScroll)};
document.querySelector('.tabs button[data-view="today"]')?.addEventListener('click',()=>requestAnimationFrame(refreshTodayAutoScroll));

let aiCreditRecheckTimer=null;
function queueAiCreditRecheck(button,delay=120000){
  if(aiCreditRecheckTimer)return;
  aiCreditRecheckTimer=setTimeout(()=>{aiCreditRecheckTimer=null;if(document.hidden||!document.querySelector('#view-admin.active')){queueAiCreditRecheck(button,15000);return}button.click()},delay);
}
function renderAiCreditStatus(service){
  const state=service.status||'unverified',blocked=state==='blocked',status=$('adminAiCreditStatus'),button=$('adminAiCreditCheck'),messages={available:'API credits are usable',blocked:'Credits or quota need attention',not_configured:'OpenAI API key is not configured',unverified:'API credits have not been verified'};
  status.textContent=messages[state]||messages.unverified;status.className=state;
  $('adminAiBalanceLink').href=service.balance_url||'https://platform.openai.com/settings/organization/billing/overview';
  button.onclick=async()=>{button.disabled=true;button.textContent='Checking…';try{const result=await api('api/v1/admin/ai-credit-check',{method:'POST',body:'{}'});toast(result.available?'AI credits are usable':'Credits are not usable yet');await loadAdminControl()}catch(error){toast(error.message)}finally{button.disabled=false;button.textContent='Recheck credits'}};
  if(blocked)queueAiCreditRecheck(button);else{clearTimeout(aiCreditRecheckTimer);aiCreditRecheckTimer=null}
}
