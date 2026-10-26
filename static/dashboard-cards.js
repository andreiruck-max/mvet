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
    status.textContent='Ordem salva na sua conta. Arraste pela alça ↕ ou use as setas do teclado.';
   }catch(_){status.textContent='Não foi possível salvar a ordem. Tente novamente.';retry.hidden=false;}
  }
  saving=false;
 }
 retry.addEventListener('click',save);
 for(const card of initial){
  const handle=document.createElement('button');handle.type='button';handle.className='card-move';handle.textContent='↕';
  handle.setAttribute('aria-label','Mover cartão '+card.querySelector('h2').textContent);handle.title='Arraste para organizar ou use as setas do teclado';card.append(handle);
  handle.addEventListener('keydown',e=>{
   const direction=['ArrowLeft','ArrowUp'].includes(e.key)?-1:['ArrowRight','ArrowDown'].includes(e.key)?1:0;
   if(!direction)return;e.preventDefault();const list=cards(),index=list.indexOf(card),target=list[index+direction];
   if(!target)return;grid.insertBefore(card,direction<0?target:target.nextSibling);handle.focus();save();
  });
  let active=false,changed=false;
  handle.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();active=true;changed=false;handle.setPointerCapture(e.pointerId);card.classList.add('moving');});
  handle.addEventListener('pointermove',e=>{
   if(!active)return;
   const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-card]');
   if(!target||target===card||target.parentNode!==grid)return;
   const list=cards();grid.insertBefore(card,list.indexOf(card)<list.indexOf(target)?target.nextSibling:target);changed=true;
  });
  const finish=()=>{if(!active)return;active=false;card.classList.remove('moving');if(changed)save();};
  handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
 }
})();
