(() => {
  const form=document.getElementById('sale-correction-form');
  if (!form) return;
  const mode=form.elements.namedItem('tax_mode');
  const refresh=()=>{
    for (const [name,choice] of [['tax_rate','rate'],['corrected_tax_amount','amount']]) {
      const input=form.elements.namedItem(name), active=mode.value===choice;
      input.closest('p').hidden=!active;input.disabled=!active;input.required=active;
    }
  };
  mode.addEventListener('change',refresh);refresh();
})();
