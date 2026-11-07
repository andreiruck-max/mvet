(() => {
  const button = document.getElementById('add-term');
  if (!button) return;
  button.addEventListener('click', () => {
    const total = document.getElementById('id_terms-TOTAL_FORMS');
    const index = Number(total.value);
    const rows = document.getElementById('term-rows');
    rows.insertAdjacentHTML('beforeend', document.getElementById('term-empty').innerHTML.replaceAll('__prefix__', index));
    total.value = index + 1;
    rows.lastElementChild.querySelector('input').focus();
  });
})();
