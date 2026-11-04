const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8');
function harness(){
  const timers=new Set(),requests=[];
  const context=vm.createContext({Map,Promise,AbortController,state:{},setTimeout:callback=>{timers.add(callback);return callback},clearTimeout:callback=>timers.delete(callback),fetch:(path,options)=>new Promise((resolve,reject)=>{const row={path,options,finish:value=>resolve({ok:true,json:async()=>value})};requests.push(row);options.signal?.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});})});
  vm.runInContext(source.slice(source.indexOf('const maxConcurrentReads='),source.indexOf('const formApi='))+'\nglobalThis.request=api;globalThis.active=()=>activeReadRequests;',context);
  return {context,requests,timers};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('standalone pages refresh only their own workspace instead of the legacy full load',async()=>{
  const performance=fs.readFileSync(path.join(__dirname,'../app/static/assets/performance.js'),'utf8');
  let view='admin-security';
  const calls=[];
  const context=vm.createContext({
    Promise,requestedRouteApplied:false,requestedView:()=>({view}),
    document:{querySelector:()=>({id:'view-today'})},
    activateRequestedView:()=>{context.requestedRouteApplied=true;calls.push('activate')},
    loadInitial:()=>calls.push('today'),loadAdminControl:()=>calls.push('admin'),
    workspaceFamily:value=>value==='finance'?'finance':null,
    loadWorkspaceView:(value,force)=>calls.push([value,force]),loadAllWorkspace:()=>calls.push('legacy-full'),
    loadSecurityWorkspace:()=>calls.push('security'),loadTvConfig:()=>calls.push('tv'),
    loadSolarWorkspace:()=>calls.push('solar'),loadWaterWorkspace:()=>calls.push('water'),
    loadViewFeatureBase:value=>calls.push(value),loadRegister:()=>calls.push('register'),
  });
  context.window=context;
  vm.runInContext(performance.slice(performance.indexOf('function dedicatedWorkspaceLoader('),performance.indexOf('async function ensureAgronomyAdminData(')),context);
  for(const [requested,expected] of [['admin-security','security'],['tv-config','tv'],['solar','solar'],['water','water'],['mail','mail'],['register','register']]){
    view=requested;context.requestedRouteApplied=false;calls.length=0;
    await context.loadAll();
    assert.deepEqual(calls,['activate',expected]);
  }
  view='finance';context.requestedRouteApplied=false;calls.length=0;await context.loadAll();
  assert.deepEqual(calls,[['finance',true]]);
});

test('fallback navigation does not attach a second loader to working primary controls',()=>{
  const bootstrap=fs.readFileSync(path.join(__dirname,'../app/static/bootstrap.js'),'utf8');
  const registrations=[];
  const buttons=[{onclick(){},addEventListener:()=>registrations.push('primary')},
                 {onclick:null,addEventListener:()=>registrations.push('fallback')}];
  const context=vm.createContext({document:{getElementById:()=>null,querySelectorAll:selector=>selector==='.tabs button'?buttons:[]}});
  vm.runInContext(bootstrap,context);
  assert.deepEqual(registrations,['fallback']);
});
test('Weather renders current readings while its comparison is still loading',async()=>{
  const performance=fs.readFileSync(path.join(__dirname,'../app/static/assets/performance.js'),'utf8');
  const calls=[],pending=[];let rendered=0;
  const context=vm.createContext({Map,Promise,workspaceLoads:new Map(),state:{year:2026},apiWriteRevision:0,
    renderWeather:()=>rendered++,renderWeatherAdvisories:()=>{},
    optionalApi:path=>{calls.push(path);return new Promise(resolve=>pending.push(resolve))}});
  vm.runInContext(performance.slice(performance.indexOf('function loadWeatherWorkspace('),performance.indexOf('function dedicatedWorkspaceLoader(')),context);
  const first=context.loadWeatherWorkspace(),second=context.loadWeatherWorkspace();
  assert.equal(first,second);
  assert.deepEqual(calls,['api/v1/weather/current','api/v1/weather/comparison?from_year=2023&to_year=2026']);
  pending[0]({current:{temp_c:8.6}});await tick();
  assert.equal(context.state.weatherCurrent.current.temp_c,8.6);assert.equal(rendered,1);
  pending[1]([{year:2025}]);await first;assert.equal(rendered,2);
});
test('duplicate refreshes share one read and repeated writes remain separate',async()=>{
  const {context,requests}=harness();
  const first=context.request('api/v1/admin/control?_=1'),second=context.request('api/v1/admin/control?_=2');
  assert.equal(requests.length,1);
  requests[0].finish({loaded:true});await Promise.all([first,second]);
  const writes=[context.request('api/v1/admin/worker-labor/one/pay',{method:'POST'}),context.request('api/v1/admin/worker-labor/one/pay',{method:'POST'})];
  assert.equal(requests.length,3);
  assert.equal(requests[1].options.signal,undefined);
  requests[1].finish({saved:true});requests[2].finish({saved:true});await Promise.all(writes);
});
test('timed-out reads release all slots so Today and Finance can load',async()=>{
  const {context,requests,timers}=harness();
  const slow=Array.from({length:4},(_,index)=>context.request(`slow/${index}`).catch(error=>error.message));
  const today=context.request('api/v1/dashboard?year=2026'),finance=context.request('api/v1/finance/dashboard?year=2026');
  assert.equal(requests.length,4);
  for(const expire of [...timers])expire();
  assert.ok((await Promise.all(slow)).every(message=>message.includes('too long')));
  await tick();
  assert.equal(requests.length,6);
  assert.ok(context.active()<=4);
  requests[4].finish({today:true});requests[5].finish({finance:true});await Promise.all([today,finance]);
  assert.equal(context.active(),0);
});
test('Payroll and Control use independent reads and preserve other loaded sections',async()=>{
  let view='view-admin-labor',release;
  const paths=[];
  const context=vm.createContext({Map,Date,apiWriteRevision:0,state:{session:{permissions:{admin:true}},adminControl:{people_directory:[{name:'David'}]}},document:{querySelector:()=>({id:view})},$:()=>null,renderAdminControl:()=>{},toast:()=>{},api:path=>{paths.push(path);return new Promise(resolve=>{release=resolve})}});
  vm.runInContext(source.slice(source.indexOf('function adminReadPath('),source.indexOf('let systemDocsLoadPromise='))+'\nglobalThis.load=loadAdminControl;',context);
  const first=context.load(),second=context.load();
  assert.deepEqual(paths,['api/v1/admin/payroll']);
  release({scope:'payroll',labor_reconciliation:[],payroll:{ready_to_pay:430}});await Promise.all([first,second]);
  assert.equal(context.state.adminControl.people_directory[0].name,'David');
  view='view-admin';const control=context.load();assert.equal(paths[1],'api/v1/admin/control/runtime');
  release({scope:'runtime',runtime:{version:'test'}});await control;
  assert.equal(context.state.adminControl.payroll.ready_to_pay,430);
});
test('approval forces a fresh read even while the old payroll snapshot is pending',async()=>{
  const {context,requests}=harness();
  const rendered=[];
  Object.assign(context,{state:{session:{permissions:{admin:true}}},document:{querySelector:()=>({id:'view-admin-labor'})},$:()=>null,renderAdminControl:()=>rendered.push(context.state.adminControl),toast:()=>{}});
  vm.runInContext(source.slice(source.indexOf('function adminReadPath('),source.indexOf('let systemDocsLoadPromise='))+'\nglobalThis.load=loadAdminControl;',context);
  const old=context.load();
  const approval=context.request('api/v1/admin/owner-labor/one/approve',{method:'POST'});
  requests[1].finish({status:'approved'});await approval;
  const fresh=context.load();
  assert.equal(requests.length,3);
  requests[0].finish({scope:'payroll',owner_labor_reviews:[{id:'one',approval_status:'draft'}]});await tick();
  assert.equal(rendered.length,0);
  requests[2].finish({scope:'payroll',owner_labor_reviews:[],worker_submissions:[{id:'one',approval_status:'approved',payment_status:'unpaid'}]});
  await Promise.all([old,fresh]);
  assert.equal(rendered.length,1);
  assert.equal(rendered[0].owner_labor_reviews.length,0);
  assert.equal(rendered[0].worker_submissions[0].approval_status,'approved');
});
test('approved cards move out of review while other work dates stay pending',()=>{
  const payroll=fs.readFileSync(path.join(__dirname,'../app/static/assets/payroll.js'),'utf8');
  const owner=fs.readFileSync(path.join(__dirname,'../app/static/assets/owner-labor-review.js'),'utf8');
  const rows=[{id:'approved',approval_status:'approved',payment_status:'unpaid',work_date:'2026-10-27'},{id:'pending',approval_status:'submitted',work_date:'2026-10-28'},{id:'paid',approval_status:'approved',payment_status:'paid',work_date:'2026-10-27'}];
  const cards=rows.map(row=>({dataset:{workerSubmission:row.id},hidden:true,removed:false,remove(){this.removed=true}}));
  const moved=[],heading={},detail={},pending={querySelector:selector=>selector.endsWith(' b')?heading:detail,remove(){this.removed=true}},empty={remove(){this.removed=true}};
  const review={querySelectorAll:()=>cards,querySelector:selector=>selector==='.worker-admin-queue'?pending:empty};
  const paymentCards={appendChild:card=>{card.hidden=false;moved.push(card)}},payments={querySelector:()=>paymentCards};
  const context=vm.createContext({Date,Set,$:id=>id==='adminTimesheetReviews'?review:payments});
  vm.runInContext(owner.slice(0,owner.indexOf('function renderPayrollReviewPeriod('))+payroll.slice(payroll.indexOf('function organizePayrollQueues('),payroll.indexOf('function byteLabel('))+'\nglobalThis.organize=organizePayrollQueues;',context);
  context.organize({owner_labor_reviews:[{id:'other-day',approval_status:'draft',work_date:'2026-10-28'}],worker_submissions:rows});
  assert.deepEqual(moved.map(card=>card.dataset.workerSubmission),['approved']);
  assert.equal(cards[1].hidden,false);
  assert.equal(cards[2].removed,true);
  assert.equal(empty.removed,true);
  assert.equal(heading.textContent,'Worker submissions awaiting approval');
});
