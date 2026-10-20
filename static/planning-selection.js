(() => {
  const form = document.getElementById('planning-export');
  if (!form) return;
  const boxes = [...document.querySelectorAll('input[name="product"][form="planning-export"]')];
  const count = document.getElementById('planning-selection-count');
  const scope = document.getElementById('export-scope');
  const buttons = [...form.querySelectorAll('[data-planning-select]')];
  const update = () => {
    const selected = boxes.filter(box => box.checked).length;
    count.textContent = selected + ' de ' + boxes.length + ' selecionados nesta página';
    buttons.forEach(button => {
      button.disabled = button.dataset.planningSelect === 'all' ? selected === boxes.length : selected === 0;
    });
  };
  buttons.forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      boxes.forEach(box => { box.checked = button.dataset.planningSelect === 'all'; });
      scope.value = 'selected';
      update();
    });
  });
  boxes.forEach(box => box.addEventListener('change', () => {
    scope.value = 'selected';
    update();
  }));
  update();
})();
