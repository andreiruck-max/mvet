(() => {
 document.getElementById('add-extra')?.addEventListener('click',()=>{
  const total=document.getElementById('id_extras-TOTAL_FORMS');
  document.getElementById('extra-rows').insertAdjacentHTML('beforeend',document.getElementById('extra-empty').innerHTML.replaceAll('__prefix__',total.value));
  total.value=Number(total.value)+1;
 });
 document.getElementById('id_location')?.addEventListener('change',()=>{
  document.querySelectorAll('.lookup small').forEach(hint=>{hint.textContent='Estoque alterado. Pesquise novamente para conferir o saldo neste estoque.';});
 });
})();
