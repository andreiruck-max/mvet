(() => {
  const form = document.getElementById('bling-period-query');
  if (!form) return;
  const start = document.getElementById('bling-start');
  const stop = document.getElementById('bling-stop');
  const progress = document.getElementById('bling-progress');
  const results = document.getElementById('bling-results');
  const fields = [...form.querySelectorAll('input, select')];
  let running = false, stopping = false, nextPage = 1, previousKey = '', finished = false;
  const counts = new Map();
  const totals = () => [...counts.values()].reduce((a, b) => [a[0] + b[0], a[1] + b[1]], [0, 0]);
  start.disabled = false;
  stop.addEventListener('click', () => {
    stopping = true; stop.disabled = true;
    progress.textContent = 'Interrompendo após concluir o lote em andamento…';
  });
  window.addEventListener('beforeunload', event => {
    if (running) { event.preventDefault(); event.returnValue = ''; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (running) return;
    const data = new FormData(form);
    const key = JSON.stringify(['start', 'end', 'source_status'].map(name => data.get(name)));
    if (key !== previousKey || finished) { nextPage = 1; counts.clear(); }
    previousKey = key; finished = false; running = true; stopping = false;
    start.disabled = true; stop.hidden = false; stop.disabled = false;
    fields.forEach(field => { field.disabled = true; });
    try {
      while (!stopping) {
        data.set('page', String(nextPage));
        const [seen, errors] = totals();
        progress.textContent = `Buscando notas… ${seen} consultadas; ${errors} pendências. Lote ${nextPage}.`;
        const response = await fetch(form.action, {method: 'POST', body: data,
          headers: {'Accept': 'application/json'}, credentials: 'same-origin'});
        if (!(response.headers.get('content-type') || '').includes('application/json')) {
          throw new Error('Sessão expirada ou resposta indisponível. Verifique o acesso e retome a busca.');
        }
        const batch = await response.json();
        if (!response.ok) throw new Error(batch.message || 'Falha na consulta.');
        if (batch.page !== nextPage) throw new Error('Resposta de lote inesperada. Retome a busca.');
        counts.set(nextPage, [batch.processed, batch.errors]);
        results.hidden = false;
        if (batch.blocked) throw new Error(batch.message || 'Consulta parcial. Retome este lote.');
        if (!batch.has_more) { finished = true; break; }
        if (batch.next_page !== nextPage + 1 || batch.next_page > 10000) {
          throw new Error('Limite ou sequência inválida. Reduza o período.');
        }
        nextPage = batch.next_page;
      }
      const [seen, errors] = totals();
      progress.textContent = `${finished ? 'Busca concluída' : 'Busca interrompida'}. ${seen} notas consultadas; ${errors} pendências. Nenhuma venda foi confirmada.`;
    } catch (error) {
      const [seen, errors] = totals();
      progress.textContent = `Busca interrompida. ${seen} consultadas; ${errors} pendências. ${error.message} As notas já consultadas estão preservadas.`;
    } finally {
      running = false; fields.forEach(field => { field.disabled = false; });
      start.disabled = false; stop.hidden = true;
      start.textContent = finished ? 'Buscar notas do período' : 'Retomar busca';
    }
  });
})();
