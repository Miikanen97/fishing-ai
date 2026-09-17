(() => {
  const form = document.getElementById('trip-form');
  if (!form) return;
  const field = name => form.elements.namedItem(name);
  const spot = field('fishing_spot');
  const sections = Array.from(form.querySelectorAll('details[data-section]'));
  const lake = field('lake');
  const initialLake = lake.value;
  let free = {location:field('location').value, latitude:field('latitude').value, longitude:field('longitude').value};
  let wasSpot = Boolean(spot.value);
  const notify = name => field(name).dispatchEvent(new Event('change', {bubbles:true}));
  function fillLake() {
    if (!initialLake && (!lake.value || lake.dataset.auto === 'true')) {
      lake.value = field('location').value.slice(0, lake.maxLength > 0 ? lake.maxLength : 150);
      lake.dataset.auto = 'true';
    }
  }
  lake.addEventListener('input', () => { lake.dataset.auto = 'false'; });
  function placeUI(changed) {
    const selected = Boolean(spot.value);
    for (const name of ['location', 'save_spot']) {
      form.querySelector('[data-field="' + name + '"]').hidden = selected;
    }
    if (changed) {
      if (selected) {
        if (!wasSpot) free = Object.fromEntries(['location','latitude','longitude'].map(name => [name,field(name).value]));
        const option = spot.selectedOptions[0];
        field('location').value = option.textContent;
        field('latitude').value = option.dataset.latitude || '';
        field('longitude').value = option.dataset.longitude || '';
      } else {
        for (const name of ['location','latitude','longitude']) field(name).value = free[name];
      }
      fillLake();
      ['location','latitude','longitude'].forEach(notify);
    }
    wasSpot = selected;
  }
  function refresh() {
    const status = document.getElementById('weather-status').textContent;
    document.getElementById('trip-weather-error').textContent = /ilman säätietoja tai|Syötä päivämäärä/.test(status) ? status : ''; 
    for (const section of sections) {
      const populated = Array.from(section.querySelectorAll('input,select,textarea')).some(input => input.type === 'checkbox' ? input.checked : input.value !== '');
      section.querySelector('[data-state]').textContent = populated ? '· Tietoja täytetty' : '';
    }
    const values = [['air_temperature','🌡','°C'],['wind_speed','💨','m/s'],['cloud_cover','☁️','%'],['precipitation','🌧','mm/h'],['air_pressure','Paine','hPa']];
    document.getElementById('trip-weather-summary').textContent = values.filter(([name]) => field(name).value !== '').map(([name,label,unit]) => label + ' ' + field(name).value + ' ' + unit).join(' · ') || 'Säätietoja ei ole vielä.';
  }
  spot.addEventListener('change', () => { placeUI(true); refresh(); });
  field('location').addEventListener('input', fillLake);
  form.querySelectorAll('[data-now]').forEach(button => button.addEventListener('click', () => {
    const now = new Date();
    field(button.dataset.now).value = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
    notify(button.dataset.now);
  }));
  function reveal(input) {
    let parent = input.parentElement;
    while (parent && parent !== form) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; }
  }
  form.addEventListener('invalid', event => reveal(event.target), true);
  form.querySelectorAll('.text-danger').forEach(reveal);
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  form.addEventListener('weather-location', refresh);
  form.addEventListener('submit', fillLake);
  new MutationObserver(refresh).observe(document.getElementById('weather-status'), {childList:true, subtree:true, characterData:true});
  placeUI(false); refresh();
})();
