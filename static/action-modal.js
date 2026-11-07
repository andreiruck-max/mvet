/* Progressive enhancement: ordinary hrefs/forms remain fully functional without JS. */
(() => {
  const embedded = window.parent !== window;
  const send = (type, extra = {}) => window.parent.postMessage({mvetAction: type, ...extra}, location.origin);
  if (document.body.dataset.modalComplete && embedded) { send('complete'); return; }
  const patterns = JSON.parse(document.getElementById('action-patterns')?.textContent || '[]').map(p => new RegExp(p));
  const eligible = url => url.origin === location.origin && patterns.some(p => p.test(url.pathname));
  const clean = href => { const url = new URL(href, location.href); url.searchParams.delete('_modal'); return url; };
  let dirty = false;
  document.addEventListener('input', event => {
    if (event.target.closest('form')?.method.toLowerCase() !== 'post') return;
    dirty = true;
    if (embedded) send('dirty');
  });
  document.addEventListener('change', event => {
    if (event.target.closest('form')?.method.toLowerCase() !== 'post') return;
    dirty = true;
    if (embedded) send('dirty');
  });
  if (embedded && document.body.dataset.modalMode) {
    send('ready', {title: document.querySelector('h1')?.textContent.trim() || document.title});
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); send('close'); } });
    document.addEventListener('submit', event => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const url = new URL(form.action, location.href);
      if (url.origin === location.origin && (eligible(url) || form.method.toLowerCase() === 'post')) { url.searchParams.set('_modal', '1'); form.action = url.href; }
      // Native form validation has already run. Do not disable named submit buttons.
      if (form.method.toLowerCase() === 'post') {
        if (form.dataset.actionSubmitting) { event.preventDefault(); return; }
        form.dataset.actionSubmitting = 'true';
        send('busy');
        setTimeout(() => { delete form.dataset.actionSubmitting; send('idle'); }, 15000);
      }
    });
    document.addEventListener('click', event => {
      const link = event.target.closest('a[href]');
      if (!link || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.hasAttribute('download') || link.target === '_blank') return;
      if (link.getAttribute('href').startsWith('#')) return;
      const url = clean(link.href);
      if (url.origin !== location.origin) return;
      event.preventDefault();
      if (/^(←\s*)?Voltar\b/i.test(link.textContent.trim())) { send('close'); return; }
      if (eligible(url)) {
        if (dirty && !confirm('Descartar as alterações ainda não salvas?')) return;
        url.searchParams.set('_modal', '1'); location.assign(url.href);
      } else send('navigate', {url: url.href});
    });
    return;
  }
  if (embedded) return;
  const dialog = document.getElementById('action-modal');
  if (!dialog || !dialog.showModal) return;
  const frame = document.getElementById('action-modal-frame');
  const status = document.getElementById('action-modal-status');
  const title = document.getElementById('action-modal-title');
  const expand = document.getElementById('action-modal-expand');
  let trigger, frameDirty = false, busy = false, timer;
  const scrollKey = 'mvet-action-scroll:' + document.body.dataset.userId + ':' + location.href;
  try {
    const previous = JSON.parse(sessionStorage.getItem(scrollKey));
    sessionStorage.removeItem(scrollKey);
    if (previous && Date.now() - previous.at < 60000) {
      requestAnimationFrame(() => {
        const link = [...document.querySelectorAll('a[href]')].find(a => a.href === previous.focus);
        link?.focus({preventScroll: true}); window.scrollTo(0, previous.y);
      });
    }
  } catch (_) {}
  const mayClose = () => {
    if (busy) { status.hidden = false; status.textContent = 'Aguarde a resposta da operação antes de fechar.'; return false; }
    return !frameDirty || confirm('Descartar as alterações ainda não salvas?');
  };
  const close = () => { if (mayClose()) dialog.close(); };
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  document.getElementById('action-modal-close').addEventListener('click', close);
  dialog.addEventListener('close', () => {
    clearTimeout(timer); frame.removeAttribute('src'); frameDirty = false; busy = false;
    document.body.classList.remove('action-modal-open'); trigger?.focus({preventScroll: true});
  });
  expand.addEventListener('click', event => {
    event.preventDefault();
    if (mayClose()) location.assign(expand.href);
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.hasAttribute('download') || (link.target && link.target !== '_self') || link.dataset.fullPage !== undefined) return;
    const url = clean(link.href);
    if (!eligible(url)) return;
    event.preventDefault();
    trigger = link; frameDirty = false; busy = false;
    title.textContent = link.textContent.trim() || 'Ação';
    expand.href = url.href;
    status.textContent = 'Carregando…'; status.hidden = false; frame.hidden = true;
    url.searchParams.set('_modal', '1'); frame.src = url.href;
    dialog.showModal(); document.body.classList.add('action-modal-open');
    timer = setTimeout(() => { status.hidden = false; status.textContent = 'A tela está demorando. Você pode fechar ou abrir nesta página.'; }, 20000);
  });
  frame.addEventListener('load', () => {
    if (!dialog.open) return;
    try {
      if (!frame.contentDocument?.body?.dataset.modalMode && !frame.contentDocument?.body?.dataset.modalComplete) {
        clearTimeout(timer); busy = false;
        status.hidden = false; status.textContent = 'Não foi possível carregar a ação. Sua sessão pode ter expirado. Use Abrir nesta página.';
      }
    } catch (_) { status.hidden = false; status.textContent = 'Não foi possível carregar. Use Abrir nesta página.'; }
  });
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== frame.contentWindow || !dialog.open) return;
    const data = event.data || {};
    if (data.mvetAction === 'ready') {
      clearTimeout(timer); frame.hidden = false; status.hidden = true; busy = false;
      // Validation responses retain dirty state until explicitly discarded or saved.
      title.textContent = data.title || title.textContent; frame.title = title.textContent;
      try {
        const current = clean(frame.contentWindow.location.href);
        if (eligible(current)) expand.href = current.href;
        frame.contentDocument.querySelector('.errorlist input, .errorlist, input:not([type="hidden"]), select, textarea, button')?.focus();
      } catch (_) {}
    } else if (data.mvetAction === 'dirty') frameDirty = true;
    else if (data.mvetAction === 'busy') busy = true;
    else if (data.mvetAction === 'idle') busy = false;
    else if (data.mvetAction === 'close') close();
    else if (data.mvetAction === 'navigate') {
      const url = clean(data.url);
      if (url.origin === location.origin && mayClose()) location.assign(url.href);
    } else if (data.mvetAction === 'complete') {
      busy = false; frameDirty = false; dialog.close();
      if (dirty) {
        const notice = document.createElement('p'); notice.className = 'notice'; notice.setAttribute('role', 'status');
        notice.textContent = 'Ação processada. Seus campos em edição foram preservados. Após salvá-los, atualize esta página para conferir os dados.';
        document.querySelector('main').prepend(notice); return;
      }
      try { sessionStorage.setItem(scrollKey, JSON.stringify({y: scrollY, at: Date.now(), focus: trigger?.href})); } catch (_) {}
      location.reload();
    }
  });
})();
