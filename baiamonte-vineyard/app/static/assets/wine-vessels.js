// Keep the liquid color consistent across operations, cellar cards and TV.
// Explicit cellar records win; older records retain a conservative variety fallback.
(function(){
  const colorFor=row=>{
    const explicit=String(row?.wine_color||'').trim().toLowerCase();
    if(['red','white','rose'].includes(explicit))return explicit;
    const text=`${row?.wine_type||''} ${row?.variety_summary||''} ${row?.contents||''} ${row?.lot_name||''}`.toLowerCase();
    if(/rosato|rosé|rose/.test(text))return'rose';
    if(/bianco|white|grecanico|carricante/.test(text))return'white';
    if(/rosso|red|nerello|grenache/.test(text))return'red';
    return'neutral';
  };
  const tint=(node,color)=>{
    if(!node)return;
    node.classList.remove('wine-red','wine-white','wine-rose','wine-neutral');
    node.classList.add(`wine-${color}`);
  };
  const apply=()=>{
    const applicationState=typeof state==='undefined'?null:state;
    const cellar=applicationState?.cellar?.tanks||[];
    document.querySelectorAll('#cellarTanks .tank-card-new').forEach((card,index)=>tint(card.querySelector('.tank-gauge'),colorFor(cellar[index]||{contents:card.textContent})));
    const agronomy=applicationState?.agronomy?.cellar?.tanks||[];
    document.querySelectorAll('#agronomyTankList .agronomy-tank-card').forEach((card,index)=>tint(card.querySelector('.tank-type-icon'),colorFor(agronomy[index]||{contents:card.textContent})));
    const tvTanks=Array.isArray(window.BaiamonteDisplayTanks)?window.BaiamonteDisplayTanks:[];
    document.querySelectorAll('#tvTanks .tv-tank').forEach((card,index)=>tint(card.querySelector('.tv-tank-vessel'),colorFor(tvTanks[index]||{contents:card.textContent})));
  };
  // Preserve the exact database selection on the TV as well. The text fallback
  // remains only for old rows that predate the wine_color field.
  if(typeof render==='function'&&document.getElementById('tvTanks')){
    const baseRender=render;
    render=function wineAwareRender(data){
      window.BaiamonteDisplayTanks=data?.cellar?.tanks||[];
      const result=baseRender(data);
      queueMicrotask(apply);
      return result;
    };
  }
  let queued=false;
  const queue=()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;apply()})};
  new MutationObserver(queue).observe(document.documentElement,{childList:true,subtree:true});
  addEventListener('DOMContentLoaded',queue,{once:true});
  window.BaiamonteWineVessels={apply,colorFor};
})();
