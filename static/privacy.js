// Local display preference only; authorization remains enforced by the server.
(() => {
  const groups = document.querySelectorAll('.report-cards, .metric-grid, .stock-totals');
  if (!groups.length) return;
  let hidden = false;
  try { hidden = localStorage.getItem('mvet-hide-totals') === '1'; } catch (_) {}
  const saved = [];
  groups.forEach(group => {
    group.querySelectorAll('b, .metric strong, .stock-totals strong, small').forEach(node => {
      if (!/R\$|%/.test(node.textContent)) return;
      const original = [...node.childNodes];
      saved.push({node, original});
    });
  });
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'privacy-toggle';
  if (!saved.length) return;
  groups[0].before(button);
  function render() {
    saved.forEach(({node, original}) => node.replaceChildren(...(hidden ? [document.createTextNode('••••••')] : original)));
    button.textContent = hidden ? 'Mostrar valores dos cartões' : 'Ocultar valores dos cartões';
    button.setAttribute('aria-pressed', String(hidden));
  }
  button.addEventListener('click', () => {
    hidden = !hidden;
    try { localStorage.setItem('mvet-hide-totals', hidden ? '1' : '0'); } catch (_) {}
    render();
  });
  render();
})();
