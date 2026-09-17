(() => {
  const key = 'fishingai-theme';
  const root = document.documentElement;
  const system = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  let preference = null;
  try { const stored = localStorage.getItem(key); if (stored === 'light' || stored === 'dark') preference = stored; } catch (_) {}
  function apply() {
    const theme = preference || (system?.matches ? 'dark' : 'light');
    root.setAttribute('data-bs-theme', theme);
    root.style.colorScheme = theme;
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.hidden = false;
      button.textContent = theme === 'dark' ? '☀️' : '🌙';
      const label = theme === 'dark' ? 'Vaihda vaaleaan teemaan' : 'Vaihda tummaan teemaan';
      button.setAttribute('aria-label', label); button.title = label;
    }
  }
  apply();
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
      preference = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(key, preference); } catch (_) {}
      apply();
    });
  });
  system?.addEventListener('change', () => { if (!preference) apply(); });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      preference = event.newValue === 'dark' || event.newValue === 'light' ? event.newValue : null;
      apply();
    }
  });
})();
