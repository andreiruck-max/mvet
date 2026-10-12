// Preferences only reorder destinations authorized and rendered by the server.
(() => {
  const nav = document.getElementById('main-navigation');
  const search = document.getElementById('navigation-search');
  if (!nav || !search) return;
  const key = 'mvet-navigation-v2-' + document.body.dataset.userId;
  const items = [...nav.children].filter(el => el.matches('a,details'));
  const menus = items.filter(el => el.matches('details'));
  const links = [...nav.querySelectorAll('a')];
  const identity = el => el.dataset.menu || new URL(el.href).pathname;
  let settings = {};
  try { const saved = JSON.parse(localStorage.getItem(key)); if (saved && typeof saved === 'object') settings = saved; } catch (_) {}
  const feedback = document.getElementById('navigation-feedback');
  const save = () => {
    try { localStorage.setItem(key, JSON.stringify(settings)); feedback.textContent = 'Ordem salva neste navegador.'; }
    catch (_) { feedback.textContent = 'Armazenamento indisponível. A ordem vale apenas nesta página.'; }
  };
  const order = ids => {
    const remaining = new Set(items);
    (Array.isArray(ids) ? ids : []).forEach(id => {
      const el = items.find(item => identity(item) === id);
      if (el && remaining.delete(el)) nav.insertBefore(el, nav.querySelector('.nav-empty'));
    });
    remaining.forEach(el => nav.insertBefore(el, nav.querySelector('.nav-empty')));
  };
  order(settings.order);
  const openMenu = target => menus.forEach(menu => { menu.open = menu === target; });
  openMenu(menus.find(menu => menu.dataset.menu === settings.open));
  menus.forEach(menu => menu.querySelector('summary').addEventListener('click', event => {
    event.preventDefault();
    openMenu(menu.open ? null : menu);
    settings.open = menu.open ? menu.dataset.menu : null;
    save();
  }));
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  let previous;
  search.addEventListener('input', () => {
    const query = normalize(search.value);
    if (query && previous === undefined) previous = menus.find(menu => menu.open) || null;
    links.forEach(link => {
      const group = link.closest('details')?.querySelector('summary')?.textContent || '';
      link.hidden = !!query && !normalize(link.textContent + ' ' + group).includes(query);
    });
    menus.forEach(menu => {
      menu.hidden = ![...menu.querySelectorAll('a')].some(link => !link.hidden);
      if (query) menu.open = !menu.hidden;
    });
    if (!query && previous !== undefined) { openMenu(previous); previous = undefined; }
    nav.querySelector('.nav-empty').hidden = links.some(link => !link.hidden);
  });
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') { search.value = ''; search.dispatchEvent(new Event('input')); }
  });
  const path = location.pathname;
  const active = links.filter(link => {
    const target = new URL(link.href).pathname;
    return target === path || (target !== '/' && target.endsWith('/') && path.startsWith(target));
  }).sort((a,b) => new URL(b.href).pathname.length - new URL(a.href).pathname.length)[0];
  if (active) {
    active.setAttribute('aria-current', 'page');
    const menu = active.closest('details');
    openMenu(menu);
    document.querySelector('.workspace-location').textContent = menu ? menu.querySelector('summary').textContent + ' / ' + active.textContent : active.textContent;
  }
  document.querySelectorAll('.workspace nav a').forEach(link => {
    if (new URL(link.href).pathname === path) link.setAttribute('aria-current','page');
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !document.querySelector('.sidebar.menu-open')) return;
    document.querySelector('.sidebar').classList.remove('menu-open');
    const toggle = document.querySelector('.menu-toggle');
    toggle.setAttribute('aria-expanded', 'false'); toggle.focus();
  });
  const editor = document.getElementById('navigation-editor');
  const edit = document.getElementById('edit-navigation');
  const list = document.getElementById('navigation-order');
  edit.hidden = false;
  edit.setAttribute('aria-controls', editor.id);
  edit.setAttribute('aria-expanded', 'false');
  let dragged;
  const commitOrder = () => {
    settings.order = [...list.children].map(row => row.dataset.id);
    order(settings.order); save();
  };
  const renderEditor = () => {
    list.replaceChildren();
    [...nav.children].filter(el => items.includes(el)).forEach(el => {
      const label = el.matches('details') ? el.querySelector('summary').textContent : el.textContent;
      const row = document.createElement('li'); row.dataset.id = identity(el); row.draggable = true;
      const text = document.createElement('span'); text.textContent = label; row.append(text);
      [['↑', 'Subir', -1], ['↓', 'Descer', 1]].forEach(([symbol, verb, direction]) => {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = symbol;
        button.setAttribute('aria-label', verb + ' ' + label);
        button.addEventListener('click', () => {
          const neighbor = direction < 0 ? row.previousElementSibling : row.nextElementSibling;
          if (!neighbor) return;
          if (direction < 0) list.insertBefore(row, neighbor); else list.insertBefore(neighbor, row);
          commitOrder(); button.focus();
        }); row.append(button);
      });
      row.addEventListener('dragstart', event => { dragged = row; event.dataTransfer.setData('text/plain', row.dataset.id); event.dataTransfer.effectAllowed = 'move'; row.classList.add('dragging'); });
      row.addEventListener('dragend', () => { row.classList.remove('dragging'); dragged = null; });
      row.addEventListener('dragover', event => { if (dragged) event.preventDefault(); });
      row.addEventListener('drop', event => {
        if (!dragged || dragged === row) return;
        event.preventDefault();
        const after = event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2;
        list.insertBefore(dragged, after ? row.nextSibling : row); commitOrder();
      });
      list.append(row);
    });
  };
  edit.addEventListener('click', () => {
    editor.hidden = !editor.hidden; edit.setAttribute('aria-expanded', String(!editor.hidden));
    edit.textContent = editor.hidden ? 'Organizar menu' : 'Concluir organização';
    if (!editor.hidden) renderEditor();
  });
  document.getElementById('reset-navigation').addEventListener('click', () => {
    order(items.map(identity)); settings.order = items.map(identity); save(); renderEditor();
  });
})();
