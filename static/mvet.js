(() => {
  document.addEventListener('click', event => {
    const input = event.target.closest('input[type="date"]');
    if (!input || input.disabled || input.readOnly || !input.showPicker) return;
    try { input.showPicker(); } catch (_) { /* Keep the native keyboard/icon fallback. */ }
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  const root = document.documentElement;
  let saved;
  try { saved = localStorage.getItem("mvet-theme"); } catch (_) {}
  const initial = saved === "dark" || saved === "light" ? saved :
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.dataset.theme = initial;
  const toggle = document.getElementById("theme-toggle");
  const update = () => {
    toggle.textContent = root.dataset.theme === "dark" ? "Modo claro" : "Modo escuro";
    toggle.setAttribute("aria-pressed", String(root.dataset.theme === "dark"));
  };
  if (toggle) {
    update();
    toggle.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("mvet-theme", root.dataset.theme); } catch (_) {}
      update();
    });
  }
  document.querySelectorAll('.nav-submenu').forEach(menu => {
    try { menu.open = localStorage.getItem('mvet-menu-' + menu.dataset.menu) === 'open'; } catch (_) {}
    menu.addEventListener('toggle', () => {
      try { localStorage.setItem('mvet-menu-' + menu.dataset.menu, menu.open ? 'open' : 'closed'); } catch (_) {}
    });
  });
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    if (new URL(link.href).pathname === window.location.pathname) { link.setAttribute("aria-current", "page"); const menu=link.closest("details"); if (menu) menu.open=true; }
  });
})();

document.querySelector('.menu-toggle')?.addEventListener('click', function () {
  const open = document.querySelector('.sidebar').classList.toggle('menu-open');
  this.setAttribute('aria-expanded', String(open));
});
document.querySelectorAll('form[method="get"]').forEach(form => {
  const period = form.querySelector('[name="period"]');
  if (!period) return;
  form.querySelectorAll('[name="start"],[name="end"]').forEach(input => {
    input.addEventListener('change', () => { period.value = ''; });
  });
});

document.querySelectorAll('form[data-auto-filter]').forEach(form => {
  let timer;
  const apply = () => {
    clearTimeout(timer);
    const start=form.elements.namedItem('start')?.value;
    const end=form.elements.namedItem('end')?.value;
    if (!form.elements.namedItem('period')?.value && start && end && start>end) return;
    if (form.checkValidity()) form.requestSubmit();
  };
  form.addEventListener('change', event => {
    if (event.target.matches('select,input[type="date"],input[type="checkbox"]')) apply();
  });
  form.querySelectorAll('input[type="text"],input[type="search"]').forEach(input => {
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(apply, 700);
    });
  });
  form.addEventListener('submit', () => clearTimeout(timer));
});
