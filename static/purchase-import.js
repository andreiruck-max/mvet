(() => {
 const form=document.getElementById('purchase-import-form');if(!form)return;
 function render(){
  form.querySelectorAll('.import-treatment').forEach(row=>{
   const mode=row.querySelector('select[name$="-mode"]').value;
   row.querySelectorAll('[data-mode]').forEach(box=>{box.hidden=box.dataset.mode!==mode;});
  });
  const bonus=form.elements.namedItem('acquisition_kind').value==='BONUS';
  document.getElementById('bonus-notice').hidden=!bonus;
  document.getElementById('purchase-import-installments').hidden=bonus;
 }
 form.addEventListener('change',render);render();
})();
