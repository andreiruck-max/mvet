(() => {
 const grid=document.getElementById('dashboard-cards'), config=document.getElementById('card-order-config');
 if(!grid || !config)return;
 const status=document.getElementById('card-order-status'),retry=document.getElementById('card-order-retry');
 const saved=JSON.parse(document.getElementById('dashboard-card-order').textContent);
 const cards=()=>[...grid.children];
 const initial=cards();
 for(const key of saved){const card=initial.find(c=>c.dataset.card===key);if(card)grid.append(card);}
 for(const card of initial){if(!saved.includes(card.dataset.card))grid.append(card);}
 let pending=false,saving=false;
 async function save(){
  pending=true;if(saving)return;saving=true;
  while(pending){
   pending=false;status.textContent='Salvando ordem…';retry.hidden=true;
   try{
    const response=await fetch(config.dataset.url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':config.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({order:cards().map(c=>c.dataset.card)})});
    if(!response.ok || !(await response.json()).saved)throw new Error();
    status.textContent='Ordem salva na sua conta. Arraste pela alça ✥ ou use as setas do teclado.';
   }catch(_){status.textContent='Não foi possível salvar a ordem. Tente novamente.';retry.hidden=false;}
  }
  saving=false;
 }
 retry.addEventListener('click',save);
 for(const card of initial){
  const handle=document.createElement('button');handle.type='button';handle.className='card-move';handle.textContent='✥';
  handle.setAttribute('aria-label','Mover cartão '+card.querySelector('h2').textContent);handle.title='Arraste para os lados, para cima ou para baixo; ou use as setas do teclado';card.append(handle);
  handle.addEventListener('keydown',e=>{
   const columns=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
   const direction={ArrowLeft:-1,ArrowRight:1,ArrowUp:-columns,ArrowDown:columns}[e.key] || 0;
   if(!direction)return;e.preventDefault();const list=cards(),index=list.indexOf(card),target=list[index+direction];
   if(!target)return;grid.insertBefore(card,direction<0?target:target.nextSibling);handle.focus();save();
  });
  let active=false,target=null;
  const clearTarget=()=>{target?.classList.remove('drop-target');target=null;};
  handle.addEventListener('pointerdown',e=>{
   if(e.button!==0)return;e.preventDefault();active=true;clearTarget();
   handle.setPointerCapture(e.pointerId);card.classList.add('moving');
  });
  handle.addEventListener('pointermove',e=>{
   if(!active)return;
   const hovered=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-card]');
   clearTarget();
   if(hovered && hovered!==card && hovered.parentNode===grid){target=hovered;target.classList.add('drop-target');}
  });
  const finish=(commit)=>{
   if(!active)return;active=false;card.classList.remove('moving');
   const destination=target;clearTarget();
   if(commit && destination){
    const list=cards();grid.insertBefore(card,list.indexOf(card)<list.indexOf(destination)?destination.nextSibling:destination);
    handle.focus();save();
   }
  };
  handle.addEventListener('pointerup',()=>finish(true));
  handle.addEventListener('pointercancel',()=>finish(false));
  handle.addEventListener('lostpointercapture',()=>finish(false));
 }
})();
