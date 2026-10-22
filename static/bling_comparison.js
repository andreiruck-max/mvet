document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('bling-comparison-filters');
  if (form) {
    ['differences', 'scope'].forEach(name => {
      const control = form.querySelector(`[name="${name}"]`);
      control.addEventListener('change', () => {
        const url = new URL(window.location.href);
        url.searchParams.delete('refresh');
        url.searchParams.set(name, name === 'differences' ? (control.checked ? 'on' : '') : control.value);
        window.location.assign(url);
      });
    });
  }
  const all = document.getElementById('bling-select-page');
  if (!all) return;
  const items = [...document.querySelectorAll('[name="tokens"][form="bling-bulk-correction"]')];
  const update = () => {
    const count = items.filter(item => item.checked).length;
    document.getElementById('bling-selected-count').textContent = `${count} selecionados`;
    all.checked = count > 0 && count === items.length;
    all.indeterminate = count > 0 && count < items.length;
  };
  all.addEventListener('change', () => { items.forEach(item => { item.checked = all.checked; }); update(); });
  items.forEach(item => item.addEventListener('change', update));
});

document.addEventListener('DOMContentLoaded', async () => {
  const form = document.getElementById('bling-bulk-run');
  if (!form) return;
  let stopped = false;
  for (const row of document.querySelectorAll('[data-bulk-index]')) {
    const output = row.querySelector('[data-bulk-result]');
    const data = new FormData(form);
    data.set('action', 'bulk_item');
    data.set('index', row.dataset.bulkIndex);
    output.textContent = 'Aplicando…';
    try {
      const response = await fetch(window.location.href, {method: 'POST', body: data, credentials: 'same-origin'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Não foi possível confirmar o resultado.');
      const labels = {DONE: 'Concluído', FAILED: 'Não aplicado', UNKNOWN: 'Conferir no Bling', PENDING: 'Pendente de conferência'};
      output.textContent = `${labels[result.status] || result.status}${result.message ? ': ' + result.message : ''}`;
    } catch (error) {
      output.textContent = `Lote interrompido: ${error.message} Confira o histórico antes de tentar novamente.`;
      stopped = true;
      break;
    }
  }
  document.getElementById('bling-bulk-status').textContent = stopped
    ? 'Lote interrompido. Os itens concluídos foram preservados; os seguintes não foram enviados.'
    : 'Lote finalizado. Confira o resultado de cada produto abaixo.';
});
