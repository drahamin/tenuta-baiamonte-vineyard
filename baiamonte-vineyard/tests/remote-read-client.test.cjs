const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/remote_static/remote-read.js'),'utf8');

function fixture(){
  class Element{constructor(){this.textContent='';this.children=[];this.listeners={};this.dataset={}}replaceChildren(...items){this.children=items}append(...items){this.children.push(...items)}addEventListener(event,fn){this.listeners[event]=fn}}
  const nodes=Object.fromEntries(['records','status','age','refresh'].map(id=>[id,new Element()]));
  const document={hidden:false,body:new Element(),listeners:{},getElementById:id=>nodes[id],createElement:()=>new Element(),addEventListener(event,fn){this.listeners[event]=fn}};
  const window={listeners:{},addEventListener(event,fn){this.listeners[event]=fn}};
  const requests=[];
  const context=vm.createContext({document,window,location:{pathname:'/labels/tank/11111111-1111-4111-8111-111111111111'},fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),AbortController,setTimeout:()=>1,clearTimeout:()=>{},setInterval:()=>1,Date,console});
  vm.runInContext(source,context);
  return {document,window,nodes,requests,context};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const valid=()=>({ok:true,json:async()=>({read_only:true,offline_cache:false,generated_at:new Date().toISOString(),tank:{name:'Allowed tank',observed_at:null}})});

test('only authorized no-cache endpoint; auth failure clears previous records',async()=>{
  const f=fixture();assert.match(f.requests[0].url,/^\/labels\/api\/tank\//);assert.equal(f.requests[0].options.cache,'no-store');assert.equal(f.requests[0].options.redirect,'error');
  f.requests[0].resolve(valid());await flush();assert.equal(f.nodes.records.children.length,1);
  vm.runInContext('refresh()',f.context);f.requests[1].resolve({ok:false});await flush();assert.equal(f.nodes.records.children.length,0);assert.match(f.nodes.status.textContent,/Unavailable or access expired/);
});
test('offline and hidden view clear data; an old in-flight reply cannot repopulate it',async()=>{
  const f=fixture();f.window.listeners.offline();f.requests[0].resolve(valid());await flush();assert.equal(f.nodes.records.children.length,0);
  vm.runInContext('refresh()',f.context);f.document.hidden=true;f.document.listeners.visibilitychange();f.requests[1].resolve(valid());await flush();assert.equal(f.nodes.records.children.length,0);
  f.document.hidden=false;f.document.listeners.visibilitychange();f.requests[2].resolve(valid());await flush();assert.equal(f.nodes.records.children.length,1);
});
test('network error and incompatible or cache-enabled payloads fail closed',async()=>{
  for(const response of [{ok:true,json:async()=>({read_only:false})},{ok:true,json:async()=>({read_only:true,offline_cache:true})}]){
    const f=fixture();f.requests[0].resolve(response);await flush();assert.equal(f.nodes.records.children.length,0);assert.equal(f.document.body.dataset.state,'unavailable');
  }
  const f=fixture();f.requests[0].reject(new Error('offline'));await flush();assert.equal(f.nodes.records.children.length,0);
});
