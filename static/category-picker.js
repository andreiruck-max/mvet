(() => {
  const originals=new WeakMap();
  const normalize=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  // Delegation also handles rows added to a manual purchase form.
  document.addEventListener('input',event=>{
    if (!event.target.matches('[data-category-search]')) return;
    const picker=event.target.closest('[data-category-picker]');
    const select=picker.querySelector('select');
    if (!originals.has(select)) originals.set(select,[...select.children].map(node=>node.cloneNode(true)));
    const query=normalize(event.target.value.trim());
    const selected=select.value;
    let count=0;
    const children=[];
    for (const original of originals.get(select)) {
      const node=original.cloneNode(true);
      if (node.tagName==='OPTGROUP') {
        for (const option of [...node.children]) {
          const matches=normalize(`${node.label} ${option.textContent}`).includes(query);
          if (matches) count++;
          if (!matches && option.value!==selected) option.remove();
        }
        if (node.children.length) children.push(node);
      } else children.push(node);
    }
    select.replaceChildren(...children);
    select.value=selected;
    picker.querySelector('[data-category-status]').textContent=
      `${count} categoria(s) encontrada(s).${selected?' Seleção atual preservada.':''}`;
  });
})();
