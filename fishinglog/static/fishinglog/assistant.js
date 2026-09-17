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

// Presentation helpers only: submission remains an explicit user action.
document.querySelectorAll('[data-question]').forEach(button => {
  button.addEventListener('click', () => {
    const question = document.getElementById('id_question');
    question.value = button.dataset.question;
    question.focus();
  });
});
document.getElementById('assistant-spot')?.addEventListener('change', function () {
  const place = document.getElementById('id_place');
  place.value = this.value;
  if (!this.value) place.focus();
});
