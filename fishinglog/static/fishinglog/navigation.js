(() => {
  const nav = document.getElementById('site-navigation');
  const button = document.getElementById('menu-toggle');
  const links = document.getElementById('navigation-links');
  if (!nav || !button || !links) return;
  const desktop = window.matchMedia('(min-width:1200px)');
  const close = () => {
    nav.classList.remove('menu-open');
    button.setAttribute('aria-expanded', 'false');
  };
  nav.classList.add('navigation-enhanced');
  button.hidden = false;
  button.addEventListener('click', () => {
    const open = button.getAttribute('aria-expanded') !== 'true';
    nav.classList.toggle('menu-open', open);
    button.setAttribute('aria-expanded', String(open));
  });
  nav.addEventListener('keydown', event => {
    if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
      close(); button.focus();
    }
  });
  links.addEventListener('click', event => { if (event.target.closest('a')) close(); });
  document.addEventListener('click', event => { if (!nav.contains(event.target)) close(); });
  nav.addEventListener('focusout', event => { if (!nav.contains(event.relatedTarget)) close(); });
  desktop.addEventListener('change', close);
  window.addEventListener('pageshow', close);
})();
