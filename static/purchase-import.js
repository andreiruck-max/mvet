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
 const addInstallment=document.getElementById('purchase-import-add-installment');
 addInstallment?.addEventListener('click',()=>{
  const count=document.getElementById('id_installments-TOTAL_FORMS');
  const template=document.getElementById('purchase-import-installment-empty');
  const rows=document.getElementById('purchase-import-installment-rows');
  if(!count||!template||!rows)return;
  const index=Number(count.value);
  if(index>=120)return;
  rows.insertAdjacentHTML('beforeend',template.innerHTML.replaceAll('__prefix__',index));
  count.value=index+1;
 });
 form.addEventListener('change',render);render();
})();
