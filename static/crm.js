(() => {
 const form=document.getElementById('crm-interaction');if(!form)return;
 const rules=JSON.parse(document.getElementById('crm-rules').textContent),result=form.elements.result,date=form.elements.next_date,occurred=form.elements.occurred_at;
 const hint=document.getElementById('crm-suggestion');
 function plus(base,days){const d=new Date(base+'T12:00:00');d.setDate(d.getDate()+days);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');}
 function update(){const rule=rules[result.value],stop=result.value==='OPT_OUT';date.disabled=stop||!!rule&&!rule.manual;document.getElementById('crm-shortcuts').hidden=stop||!!rule&&!rule.manual;
  if(stop){hint.textContent='Não contatar: nenhuma nova recorrência será criada.';date.value='';return;}
  if(!rule){hint.textContent='Escolha um resultado para ver a próxima data sugerida.';return;}
  const suggested=date.value&&!date.disabled?date.value:plus(occurred.value.slice(0,10)||form.dataset.today,rule.days);
  hint.textContent='Próximo contato '+(date.value&&!date.disabled?'escolhido':'sugerido')+': '+suggested.split('-').reverse().join('/')+(rule.manual?'':' · data definida pelo Master');
 }
 result.addEventListener('change',()=>{date.value='';update();});date.addEventListener('change',update);occurred.addEventListener('change',update);
 form.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>{date.value=plus(form.dataset.today,Number(button.dataset.days));update();}));
 document.getElementById('crm-default').addEventListener('click',()=>{date.value='';update();});
 document.getElementById('crm-choose').addEventListener('click',()=>{date.focus();try{date.showPicker();}catch{}});update();
})();
