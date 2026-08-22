// Preserve deliberate selections when live renderers rebuild option elements.
(function(){
  const values=new WeakMap(),ids=new Map();
  function remember(select){if(!(select instanceof HTMLSelectElement))return;values.set(select,select.value);if(select.id)ids.set(select.id,select.value)}
  function restore(select){if(!(select instanceof HTMLSelectElement))return;const value=values.get(select)??(select.id?ids.get(select.id):undefined);if(value===undefined||select.value===value||![...select.options].some(option=>option.value===value))return;select.value=value}
  document.addEventListener('change',event=>remember(event.target),true);
  document.addEventListener('reset',event=>setTimeout(()=>event.target.querySelectorAll('select').forEach(remember)),true);
  new MutationObserver(mutations=>{const selects=new Set();for(const mutation of mutations){const closest=mutation.target instanceof Element?mutation.target.closest('select'):null;if(closest)selects.add(closest);for(const node of mutation.addedNodes)if(node instanceof Element){if(node.matches('select'))selects.add(node);node.querySelectorAll?.('select').forEach(select=>selects.add(select))}}selects.forEach(restore)}).observe(document.documentElement,{childList:true,subtree:true});
})();
