(() => {
 const form=document.getElementById('purchase-form');if(!form)return;
 function scaled(raw,places){
  const s=(raw||'0').trim().replace(',','.');if(!/^\d*(\.\d*)?$/.test(s))throw new Error();
  const [whole='0',fraction='']=s.split('.');if(fraction.length>places)throw new Error();
  return BigInt(whole||'0')*10n**BigInt(places)+BigInt(fraction.padEnd(places,'0')||'0');
 }
 function value(name,places){return scaled(form.elements.namedItem(name)?.value,places);}
 function format(cents){return (cents/100n).toString()+','+(cents%100n).toString().padStart(2,'0');}
 function total(){
  let sum=0n;const count=Number(form.elements.namedItem('form-TOTAL_FORMS').value);
  for(let i=0;i<count;i++){if(form.elements.namedItem(`form-${i}-DELETE`)?.checked)continue;sum+=(value(`form-${i}-quantity`,4)*value(`form-${i}-unit_cost`,6)+50000000n)/100000000n;}
  return sum-value('discount',2)+value('freight',2)+value('other_costs',2);
 }
 function update(){try{const t=total();document.getElementById('purchase-total').textContent=t<0n?'Confira o desconto: total negativo.':'Total previsto da compra: R$ '+format(t)+'. Confira o rateio ao salvar.';}catch{document.getElementById('purchase-total').textContent='Confira os valores e casas decimais para calcular o total.';}}
 form.addEventListener('input',update);form.addEventListener('change',update);
 document.getElementById('add-component').addEventListener('click',update);
 document.getElementById('add-installment').addEventListener('click',()=>{
  const totalForms=document.getElementById('id_installments-TOTAL_FORMS'),index=Number(totalForms.value);
  document.getElementById('installment-rows').insertAdjacentHTML('beforeend',document.getElementById('installment-empty').innerHTML.replaceAll('__prefix__',index));totalForms.value=index+1;
  try{let remaining=total();for(let i=0;i<index;i++)if(!form.elements.namedItem(`installments-${i}-DELETE`)?.checked)remaining-=value(`installments-${i}-amount`,2);if(remaining>0n)form.elements.namedItem(`installments-${index}-amount`).value=format(remaining).replace(',','.');}catch{}
  form.elements.namedItem(`installments-${index}-due_date`).value=document.getElementById('id_date').value;
 });update();
})();
