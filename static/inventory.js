(() => {
 const endpoint='/api/v1/produtos/';
 const labels=JSON.parse(document.getElementById('component-labels')?.textContent || '{}');
 function enhance(root=document) {
  root.querySelectorAll('input[data-product-lookup]:not([data-ready])').forEach(hidden=>{
   hidden.dataset.ready='1';
   const wrap=document.createElement('div');wrap.className='field lookup';
   const label=document.createElement('label');label.textContent=hidden.name.includes('target')?'Produto de destino':hidden.name.includes('component')?'Componente':'Produto';
   const input=document.createElement('input');input.type='search';input.placeholder='Digite SKU ou nome e selecione';input.autocomplete='off';input.id=hidden.id+'_search';label.htmlFor=input.id;
   const results=document.createElement('div');results.className='lookup-results';
   const hint=document.createElement('small');hint.className='muted';hint.setAttribute('aria-live','polite');
   if(hidden.value) input.value=labels[hidden.value] || 'Produto selecionado #'+hidden.value;
   wrap.append(label,input,results,hint);hidden.after(wrap);
   let timer,controller;
   input.addEventListener('input',()=>{
    hidden.value='';clearTimeout(timer);controller?.abort();results.replaceChildren();hint.textContent='';
    if(!input.value.trim())return;
    timer=setTimeout(async()=>{
     controller=new AbortController();
     try {
      const response=await fetch(endpoint+'?q='+encodeURIComponent(input.value),{signal:controller.signal});
      if(!response.ok)throw new Error();
      const data=await response.json();
      for(const p of data.results){const button=document.createElement('button');button.type='button';button.textContent=p.label;button.addEventListener('click',()=>{hidden.value=p.id;input.value=p.label;hint.textContent='Disponível: '+p.quantity+(p.cost!==undefined?' · Custo: R$ '+p.cost:'');results.replaceChildren();});results.append(button);}
      if(!data.results.length)hint.textContent='Nenhum produto encontrado.';
     }catch(e){if(e.name!=='AbortError')hint.textContent='Não foi possível pesquisar. Tente novamente.';}
    },200);
   });
  });
 }
 enhance();
 document.getElementById('add-component')?.addEventListener('click',()=>{const total=document.getElementById('id_form-TOTAL_FORMS');const rows=document.getElementById('component-rows');rows.insertAdjacentHTML('beforeend',document.getElementById('component-empty').innerHTML.replaceAll('__prefix__',total.value));total.value=Number(total.value)+1;enhance(rows);});
 const kind=document.getElementById('id_kind');
 if(kind){const update=()=>{const k=kind.value;for(const [name,visible] of Object.entries({cost:['OPENING','RECEIPT','ADJUST_IN','REVALUE'].includes(k),target_location:['TRANSFER','SPLIT'].includes(k),target_quantity:k==='SPLIT',quantity:k!=='REVALUE'})){const el=document.querySelector('[data-field="'+name+'"]');if(el)el.hidden=!visible;}const target=document.getElementById('id_target_product');if(target?.nextElementSibling)target.nextElementSibling.hidden=k!=='SPLIT';if(k==='REVALUE')document.getElementById('id_quantity').value='0';};kind.addEventListener('change',update);update();}
})();
