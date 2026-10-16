(() => {
  const form=document.getElementById('expense-bulk-form');
  if (!form) return;
  const all=document.getElementById('expense-select-all');
  const boxes=[...form.querySelectorAll('[name="expense_ids"]')];
  const count=document.getElementById('expense-selection-count');
  const update=() => {
    const selected=boxes.filter(box=>box.checked).length;
    count.textContent=`${selected} despesa(s) selecionada(s) nesta página`;
    all.checked=boxes.length>0 && selected===boxes.length;
    all.indeterminate=selected>0 && selected<boxes.length;
    form.querySelector('button').disabled=selected===0;
  };
  all.addEventListener('change',()=>{boxes.forEach(box=>box.checked=all.checked);update();});
  boxes.forEach(box=>box.addEventListener('change',update));
  update();
})();
