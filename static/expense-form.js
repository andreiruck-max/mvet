(() => {
  const suggestions = document.getElementById('category-code-suggestions');
  if (suggestions) {
    const choices = JSON.parse(suggestions.textContent);
    const code = document.getElementById('id_code');
    const parent = document.getElementById('id_parent');
    let manual = code.value !== (choices[parent.value]?.code || '');
    code.addEventListener('input', () => { manual = true; });
    const suggest = () => { code.value = choices[parent.value]?.code || ''; };
    parent.addEventListener('change', () => {
      if (!manual) suggest();
      const nature = choices[parent.value]?.nature;
      if (nature) document.getElementById('id_nature').value = nature;
    });
    document.getElementById('suggest-category-code').addEventListener('click', () => {
      manual = false; suggest();
    });
  }
  const search = document.getElementById('category-search');
  if (search) {
    const select = document.getElementById('id_category');
    const options = Array.from(select.options, option => option.cloneNode(true));
    const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    search.addEventListener('input', () => {
      const query = normalize(search.value.trim()), selected = select.value;
      const matches = options.filter(option => option.value && normalize(option.textContent).includes(query));
      select.replaceChildren(...options.filter(option => !option.value || option.value === selected || matches.includes(option)).map(option => option.cloneNode(true)));
      select.value = selected;
      document.getElementById('category-search-status').textContent = `${matches.length} categoria(s) encontrada(s). A seleção atual é preservada.`;
    });
  }
})();
