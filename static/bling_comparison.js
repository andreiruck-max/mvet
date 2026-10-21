document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('bling-comparison-filters');
  if (!form) return;
  const checkbox = form.querySelector('[name="differences"]');
  checkbox.addEventListener('change', () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('refresh');
    url.searchParams.set('differences', checkbox.checked ? 'on' : '');
    window.location.assign(url);
  });
});
