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
  const context=vm.createContext({Map,Date,state:{session:{permissions:{admin:true}},adminControl:{people_directory:[{name:'David'}]}},document:{querySelector:()=>({id:view})},$:()=>null,renderAdminControl:()=>{},toast:()=>{},api:path=>{paths.push(path);return new Promise(resolve=>{release=resolve})}});
  vm.runInContext(source.slice(source.indexOf('function adminReadPath('),source.indexOf('let systemDocsLoadPromise='))+'\nglobalThis.load=loadAdminControl;',context);
  const first=context.load(),second=context.load();
  assert.deepEqual(paths,['api/v1/admin/payroll']);
  release({scope:'payroll',labor_reconciliation:[],payroll:{ready_to_pay:430}});await Promise.all([first,second]);
  assert.equal(context.state.adminControl.people_directory[0].name,'David');
  view='view-admin';const control=context.load();assert.equal(paths[1],'api/v1/admin/control/runtime');
  release({scope:'runtime',runtime:{version:'test'}});await control;
  assert.equal(context.state.adminControl.payroll.ready_to_pay,430);
});
