(() => {
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
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    if (new URL(link.href).pathname === window.location.pathname) link.setAttribute("aria-current", "page");
  });
})();
