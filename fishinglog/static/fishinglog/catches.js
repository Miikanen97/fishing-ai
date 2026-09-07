(() => {
  const form = document.getElementById('catch-batch-form');
  if (!form) return;
  const rows = document.getElementById('fish-forms');
  const template = document.getElementById('fish-template');
  const total = form.elements.namedItem('catches-TOTAL_FORMS');
  const max = Number(form.elements.namedItem('catches-MAX_NUM_FORMS').value);
  const outcome = form.elements.namedItem('no_catch');
  const fieldset = document.getElementById('fish-fields');
  const add = document.getElementById('add-fish');
  const status = document.getElementById('fish-status');

  function renumber() {
    [...rows.children].forEach((row, i) => {
      for (const element of row.querySelectorAll('[name], [id], [for], [aria-describedby]')) {
        for (const attribute of ['name', 'id', 'for', 'aria-describedby']) {
          if (element.hasAttribute(attribute)) {
            element.setAttribute(attribute, element.getAttribute(attribute).replace(/catches-(?:\d+|__prefix__)-/g, 'catches-' + i + '-'));
          }
        }
      }
      row.setAttribute('aria-label', 'Kala ' + (i + 1));
      row.querySelector('.fish-heading').textContent = 'Kala ' + (i + 1);
      row.querySelector('.remove-fish').setAttribute('aria-label', 'Poista kala ' + (i + 1) + ' lomakkeelta');
    });
    total.value = rows.children.length;
    add.disabled = rows.children.length >= max;
  }

  add.addEventListener('click', () => {
    if (rows.children.length >= max) return;
    rows.append(template.content.cloneNode(true));
    renumber();
    rows.lastElementChild.querySelector('input').focus();
    status.textContent = 'Kala lisätty. Lomakkeita yhteensä ' + rows.children.length + '.';
  });
  rows.addEventListener('click', event => {
    const button = event.target.closest('.remove-fish');
    if (!button) return;
    button.closest('.fish-row').remove();
    renumber();
    add.focus();
    status.textContent = 'Kalalomake poistettu. Lomakkeita jäljellä ' + rows.children.length + '.';
  });
  function toggleOutcome() {
    fieldset.hidden = outcome.checked;
    fieldset.disabled = outcome.checked;
    status.textContent = outcome.checked ? 'Reissu merkitään saaliittomaksi. Kalalomakkeita ei tallenneta.' : '';
  }
  outcome.addEventListener('change', toggleOutcome);
  renumber();
  toggleOutcome();
})();

