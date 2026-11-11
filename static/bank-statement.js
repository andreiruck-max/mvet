(() => {
  document.querySelectorAll('[data-bank-widget]').forEach(widget => {
    if (widget.dataset.initialized) return;
    widget.dataset.initialized = '1';
    const result = widget.querySelector('[data-bank-result]');
    const message = widget.querySelector('[data-bank-message]');
    const form = widget.querySelector('[data-bank-refresh]');
    let timer, polls = 0;
    async function status() {
      const url = new URL(widget.dataset.statusUrl, location.origin);
      url.search = location.search;
      url.searchParams.set('compact', widget.dataset.compact);
      const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Não foi possível verificar a atualização. O histórico salvo foi preservado.');
      const data = await response.json();
      result.innerHTML = data.html;
      if (data.busy && ++polls < 120) timer = setTimeout(() => status().catch(showError), 5000);
      else if (data.busy) message.textContent = 'A consulta continua em segundo plano. Reabra a conta para acompanhar.';
      else message.textContent = '';
    }
    function showError(error) { message.textContent = error.message || 'Falha na consulta. Histórico salvo preservado.'; }
    async function refresh(automatic) {
      clearTimeout(timer); polls = 0;
      if (!form) return;
      const body = new FormData(form);
      const filters = new URLSearchParams(location.search);
      ['period','start','end'].forEach(key => { if (filters.has(key)) body.set(key, filters.get(key)); });
      if (!body.get('period') && !body.get('start')) body.set('period','month');
      body.set('mode', automatic ? 'automatic' : 'manual');
      message.textContent = 'Solicitando atualização em segundo plano…';
      const response = await fetch(widget.dataset.refreshUrl, {method:'POST',body,credentials:'same-origin',headers:{'Accept':'application/json'}});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Sessão expirada ou acesso recusado. Entre novamente para atualizar.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Não foi possível iniciar a atualização.');
      await status();
    }
    if (form) form.addEventListener('submit', event => { event.preventDefault(); refresh(false).catch(showError); });
    if (widget.dataset.automatic === '1') refresh(true).catch(showError);
    else status().catch(showError);
    window.addEventListener('pagehide', () => clearTimeout(timer), {once:true});
  });
})();
