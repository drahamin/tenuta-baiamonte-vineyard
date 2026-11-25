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

function wallHarness(){
 const revoked=[];
 class Tile{
  constructor(){this.dataset={};this.status={textContent:''};this.name={textContent:''};this.image={dataset:{},src:'logo',isConnected:true,closest:()=>this};this.classList={add:()=>{},remove:()=>{}}}
  querySelector(selector){return selector==='img'?this.image:selector==='figcaption b'?this.name:this.status}
  set innerHTML(value){this.html=value}
 }
 const wall={tiles:[],querySelectorAll:()=>wall.tiles,replaceChildren:(...tiles)=>{for(const tile of wall.tiles)if(!tiles.includes(tile))tile.image.isConnected=false;wall.tiles=tiles},set innerHTML(value){wall.html=value;wall.tiles=[]}};
 const context={$:()=>wall,document:{createElement:()=>new Tile()},URL:{revokeObjectURL:url=>revoked.push(url)},esc:String,cameraSnapshotSource:()=>''};
 const first=source.indexOf('function renderCameraWall('),last=source.indexOf('function setCameraPages(',first);
 const draw=vm.runInNewContext(source.slice(first,last)+';renderCameraWall',context);
 return{wall,draw,revoked};
}
test('metadata refresh keeps decoded pictures and image nodes on Main cameras',()=>{
 const {wall,draw,revoked}=wallHarness(),cameras=[{entity_id:'camera.kitchen',name:'Kitchen',available:true,snapshot_updated_at:'old'}];
 draw('main',cameras,'Main');const tile=wall.tiles[0],image=tile.image;image.dataset.objectUrl='blob:retained';image.src='blob:retained';image.dataset.refreshedAt=String(Date.now());
 draw('main',[{...cameras[0],snapshot_updated_at:'new',battery:90}],'Main');
 assert.equal(wall.tiles[0],tile);assert.equal(wall.tiles[0].image,image);assert.equal(image.src,'blob:retained');assert.equal(tile.dataset.cameraSourceVersion,':new');assert.equal(revoked.length,0);
});
test('camera reorder preserves frames and removal releases only removed blobs',()=>{
 const {wall,draw,revoked}=wallHarness(),a={entity_id:'camera.a',name:'A'},b={entity_id:'camera.b',name:'B'};
 draw('main',[a,b],'Main');const [ta,tb]=wall.tiles;ta.image.dataset.objectUrl='blob:a';tb.image.dataset.objectUrl='blob:b';
 draw('main',[b,a],'Main');assert.equal(wall.tiles[0],tb);assert.equal(wall.tiles[1],ta);assert.equal(revoked.length,0);
 draw('main',[b],'Main');assert.deepEqual(revoked,['blob:a']);assert.equal(wall.tiles[0],tb);
});
function queueHarness(images){
 const calls=[],context={screen:12,cameraScreens:[3,4,12],cameraRefreshInFlight:false,cameraPageNext:{3:0,4:0,12:0},cameraRefreshSeconds:300,document:{querySelectorAll:()=>images},setTimeout:()=>{},Date};
 context.loadCameraTile=async(image)=>{calls.push(image.id);image.dataset.objectUrl='blob:'+image.id;image.dataset.refreshedAt=String(Date.now());image.dataset.loadedSourceVersion=image.tile.dataset.cameraSourceVersion;if(context.switchAfterFirst){context.screen=0;context.switchAfterFirst=false}};
 const first=source.indexOf('async function refreshCameras('),last=source.indexOf('\nfunction ',first);
 const refresh=vm.runInNewContext(source.slice(first,last)+';refreshCameras',context);
 return{calls,context,refresh};
}
function queueImage(id){const tile={dataset:{cameraSourceVersion:'v1'}};return{id,tile,dataset:{},closest:()=>tile}}
test('rotation resumes with unloaded cameras instead of restarting at the slow first tile',async()=>{
 const images=['a','b','c'].map(queueImage),{calls,context,refresh}=queueHarness(images);context.switchAfterFirst=true;
 await refresh();assert.deepEqual(calls,['a']);context.screen=12;await refresh();assert.deepEqual(calls,['a','b','c']);
});
test('missing or changed pictures bypass the refresh interval while loaded frames remain',async()=>{
 const images=['a','b'].map(queueImage),{calls,refresh}=queueHarness(images);
 await refresh();await refresh();assert.deepEqual(calls,['a','b']);
 images[1].tile.dataset.cameraSourceVersion='v2';await refresh();assert.deepEqual(calls,['a','b','b']);
 const extra=queueImage('c');images.push(extra);await refresh();assert.deepEqual(calls,['a','b','b','c']);
});
