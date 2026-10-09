(() => {
 const form=document.getElementById('purchase-import-form');if(!form)return;
 function render(){
  const supplierBox=document.getElementById('new-supplier-fields');
  const creating=form.elements.namedItem('create_supplier')?.checked;
  if(supplierBox){supplierBox.hidden=!creating;supplierBox.querySelectorAll('input,select,textarea').forEach(input=>input.disabled=!creating);}
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
