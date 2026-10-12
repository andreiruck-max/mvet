(() => {
  const form = document.getElementById('access-editor');
  if (!form) return;
  const options = [...form.querySelectorAll('.permission-option')];
  const profiles = JSON.parse(document.getElementById('access-profiles').textContent);
  const profile = document.getElementById('access-profile');
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const summary = () => {
    const selected = options.filter(option => option.querySelector('input').checked);
    const granted = new Set(selected.map(option => option.querySelector('input').value));
    document.getElementById('access-summary').textContent = `${selected.length} permissões marcadas · ${selected.filter(option => option.dataset.sensitive === 'true').length} sensíveis.`;
    const missing = selected.filter(option => option.dataset.requires && option.dataset.requires.split(',').some(code => !granted.has(code)));
    document.getElementById('access-dependencies').textContent = missing.length ? `${missing.length} permissões selecionadas dependem de outros acessos desmarcados. Confira “Para utilizar” em cada opção; esses acessos não serão concedidos automaticamente.` : '';
  };
  profile.addEventListener('change', () => {
    document.getElementById('profile-description').textContent = profiles[profile.value]?.description || 'Escolha um perfil e revise as permissões antes de salvar.';
  });
  document.getElementById('apply-access-profile').addEventListener('click', () => {
    const chosen = profiles[profile.value];
    if (!chosen) return;
    options.forEach(option => { const input = option.querySelector('input'); input.checked = chosen.codes.includes(input.value.replace('core.','')); });
    summary();
  });
  form.querySelectorAll('[data-permissions]').forEach(button => button.addEventListener('click', () => {
    button.closest('fieldset').querySelectorAll('input[type=checkbox]').forEach(input => { input.checked = button.dataset.permissions === 'all'; });
    summary();
  }));
  document.getElementById('permission-search').addEventListener('input', event => {
    const query = normalize(event.target.value.trim());
    options.forEach(option => { option.hidden = !normalize(option.textContent).includes(query); });
    form.querySelectorAll('.permission-group').forEach(group => { group.hidden = ![...group.querySelectorAll('.permission-option')].some(option => !option.hidden); });
  });
  form.addEventListener('change',summary);summary();
})();
