document.getElementById('assistant-form').addEventListener('submit', function (event) {
  if (this.dataset.pending === 'true') { event.preventDefault(); return; }
  this.dataset.pending = 'true';
  this.querySelector('button[type="submit"]').disabled = true;
  document.getElementById('assistant-progress').textContent = 'Haetaan tietoja ja muodostetaan vastausta…';
});
window.addEventListener('pageshow', function () {
  document.getElementById('assistant-form').dataset.pending = 'false';
  document.querySelector('#assistant-form button[type="submit"]').disabled = false;
  document.getElementById('assistant-progress').textContent = '';
});
