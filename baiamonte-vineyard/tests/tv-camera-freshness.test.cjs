const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/display.js'),'utf8');
const start=source.indexOf('function cameraImageTime('),end=source.indexOf('async function refreshCameras(',start);
async function render(capturedAt){
  const classes=new Set(['unavailable','placeholder']),status={textContent:''};
  const tile={dataset:{camera:'camera.example',cameraCapturedAt:new Date().toISOString()},querySelector:()=>status,classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}};
  const image={dataset:{},closest:()=>tile};
  const context={displayTimeZone:"Europe/Rome",screen:3,cameraRefreshSeconds:300,cameraFailureState:new Map(),AbortController,setTimeout:()=>1,clearTimeout:()=>{},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},fetch:async()=>({ok:true,headers:{get:k=>k==='X-Baiamonte-Camera'?'fresh':capturedAt},blob:async()=>({})})};
  const load=vm.runInNewContext(source.slice(start,end)+';loadCameraTile',context);
  await load(image,3);
  return {status:status.textContent,unavailable:classes.has('unavailable')};
}
test('missing response time cannot borrow a current tile timestamp',async()=>{
 const result=await render(null);assert.equal(result.unavailable,true);assert.match(result.status,/CAPTURE TIME UNKNOWN/);assert.doesNotMatch(result.status,/RECENT VIEW/);
});
test('future timestamp does not make a zero-age current view',async()=>{
 const result=await render(new Date(Date.now()+3600000).toISOString());assert.equal(result.unavailable,true);assert.match(result.status,/CAPTURE TIME UNKNOWN/);
});
test('old images remain visibly retained',async()=>{
 const result=await render(new Date(Date.now()-172800000).toISOString());assert.equal(result.unavailable,true);assert.match(result.status,/LAST IMAGE/);
});
test('a confirmed current response can show a current image',async()=>{
 const result=await render(new Date(Date.now()-60000).toISOString());assert.equal(result.unavailable,false);assert.match(result.status,/IMAGE/);
});
