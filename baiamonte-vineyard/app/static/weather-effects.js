(function(){
  'use strict';
  const active=new WeakMap(),rainScenes=new Set(['drizzle','rain','pouring','storm','sleet']);
  const reduced=()=>document.documentElement.dataset.lowPower==='true'||(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  function stop(node){const controller=active.get(node);if(!controller)return;controller.stopped=true;cancelAnimationFrame(controller.frame);controller.resizeObserver?.disconnect();controller.intersectionObserver?.disconnect();if(controller.resizeHandler)window.removeEventListener('resize',controller.resizeHandler);controller.canvas.remove();active.delete(node);node.classList.remove('canvas-rain')}
  function apply(node,scene,options={}){
    if(!node)return;
    if(!rainScenes.has(scene)||reduced()){stop(node);return}
    const existing=active.get(node);
    if(existing){existing.scene=scene;existing.windKph=Number(options.windKph)||0;node.classList.add('canvas-rain');return}
    const canvas=document.createElement('canvas'),context=canvas.getContext('2d',{alpha:true}),controller={canvas,context,scene,windKph:Number(options.windKph)||0,large:Boolean(options.large),drops:[],width:0,height:0,dpr:1,last:0,frame:0,stopped:false,visible:true};
    if(!context)return;
    canvas.className='weather-canvas';canvas.setAttribute('aria-hidden','true');node.appendChild(canvas);node.classList.add('canvas-rain');active.set(node,controller);
    const reset=(drop,initial=false)=>{const depth=.12+Math.random()*.88,intensity=controller.scene==='drizzle'?.48:controller.scene==='pouring'?1.15:controller.scene==='storm'?1.02:.78;drop.depth=depth;drop.x=Math.random()*(controller.width+80)-40;drop.y=initial?Math.random()*controller.height:-30-Math.random()*controller.height*.25;drop.length=(5+depth*17)*intensity;drop.speed=(95+depth*410)*intensity;drop.opacity=(.045+depth*.24)*(controller.scene==='drizzle'?.55:controller.scene==='pouring'?1.12:1);drop.width=.45+depth*.72};
    const resize=()=>{const rect=node.getBoundingClientRect();if(!rect.width||!rect.height)return;controller.width=rect.width;controller.height=rect.height;controller.dpr=Math.min(window.devicePixelRatio||1,controller.large?1.25:1.5);canvas.width=Math.round(rect.width*controller.dpr);canvas.height=Math.round(rect.height*controller.dpr);canvas.style.width=`${rect.width}px`;canvas.style.height=`${rect.height}px`;context.setTransform(controller.dpr,0,0,controller.dpr,0,0);const area=rect.width*rect.height,density=controller.large?.000105:.00022,target=Math.max(24,Math.min(controller.large?170:100,Math.round(area*density)));controller.drops=Array.from({length:target},()=>{const drop={};reset(drop,true);return drop})};
    resize();
    if(window.ResizeObserver){controller.resizeObserver=new ResizeObserver(resize);controller.resizeObserver.observe(node)}else{controller.resizeHandler=resize;window.addEventListener('resize',resize,{passive:true})}
    if(window.IntersectionObserver){controller.intersectionObserver=new IntersectionObserver(entries=>{controller.visible=Boolean(entries[0]?.isIntersecting)});controller.intersectionObserver.observe(node)}
    const draw=time=>{if(controller.stopped)return;controller.frame=requestAnimationFrame(draw);if(!controller.visible||document.hidden||time-controller.last<30)return;const dt=Math.min(.05,(time-controller.last||30)/1000);controller.last=time;context.clearRect(0,0,controller.width,controller.height);context.lineCap='round';const wind=Math.max(-35,Math.min(35,controller.windKph))*.024;
      for(const drop of controller.drops){drop.y+=drop.speed*dt;drop.x+=wind*drop.speed*dt;const drift=wind*drop.length;context.beginPath();context.moveTo(drop.x,drop.y);context.lineTo(drop.x+drift,drop.y+drop.length);context.lineWidth=drop.width;context.strokeStyle=`rgba(205,226,235,${drop.opacity.toFixed(3)})`;context.stroke();if(drop.y>controller.height+drop.length||drop.x>controller.width+70||drop.x<-70)reset(drop)}
    };
    controller.frame=requestAnimationFrame(draw)
  }
  function derived(temp,humidity){const t=Number(temp),rh=Number(humidity);if(!Number.isFinite(t)||!Number.isFinite(rh)||rh<=0)return{dewPoint:null,vpd:null};const gamma=Math.log(Math.min(100,rh)/100)+(17.625*t)/(243.04+t),dewPoint=243.04*gamma/(17.625-gamma),saturation=.6108*Math.exp(17.27*t/(t+237.3));return{dewPoint,vpd:saturation*(1-Math.min(100,rh)/100)}}
  function age(value){if(!value)return'Reading time unavailable';const at=new Date(value),seconds=(Date.now()-at.getTime())/1000;if(!Number.isFinite(seconds))return'Reading time unavailable';if(seconds<90)return'Updated just now';if(seconds<5400)return`Updated ${Math.max(1,Math.round(seconds/60))} min ago`;if(seconds<129600)return`Updated ${Math.round(seconds/3600)} hr ago`;return`Updated ${at.toLocaleDateString()}`}
  const condition=value=>String(value||'Current conditions').replaceAll('_',' ').replaceAll('-',' ');
  const romeHour=()=>Number(new Intl.DateTimeFormat('en',{timeZone:'Europe/Rome',hour:'2-digit',hourCycle:'h23'}).format(new Date()));
  function updateHeroPeriod(value=''){const hero=document.querySelector('.today-hero');if(!hero)return false;const normalized=String(value||'').toLowerCase(),night=/clear[-_ ]?night|night/.test(normalized)||romeHour()<6||romeHour()>=20;hero.classList.toggle('is-night',night);hero.classList.toggle('is-day',!night);hero.dataset.dayPeriod=night?'night':'day';return night}
  window.BaiamonteWeatherEffects={apply,stop,derived,age,condition,romeHour,updateHeroPeriod}
})();
