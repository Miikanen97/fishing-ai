(() => {
  const button = document.getElementById('fetch-weather');
  if (!button) return;
  const status = document.getElementById('weather-status');
  const form = button.closest('form');
  const auto = document.getElementById('auto-weather');
  const fieldNames = ['air_temperature', 'wind_speed', 'wind_gust', 'wind_direction', 'air_pressure', 'cloud_cover', 'precipitation', 'weather', 'weather_latitude', 'weather_longitude'];
  const input = name => form.elements.namedItem(name);
  const dirty = new Set(fieldNames.filter(name => input(name).value !== ''));
  let timer, controller, generation = 0;
  const query = () => new URLSearchParams({
    date: input('date').value,
    time: input('start_time').value,
    place: input('weather_place').value.trim() || input('location').value.trim(),
    latitude: input('latitude').value, longitude: input('longitude').value
  });
  function updateCompass() {
    const value = input('wind_direction').value.replace(',', '.');
    const number = Number(value);
    const names = ['pohjoinen', 'koillinen', 'itä', 'kaakko', 'etelä', 'lounas', 'länsi', 'luode'];
    document.getElementById('wind-compass').textContent = value && Number.isFinite(number) && number >= 0 && number <= 360
      ? names[Math.floor((number % 360 + 22.5) / 45) % 8] : '';
  }
  fieldNames.forEach(name => input(name).addEventListener('input', () => { dirty.add(name); updateCompass(); }));
  function cancel() {
    generation++;
    clearTimeout(timer);
    if (controller) controller.abort();
    button.disabled = false;
    button.textContent = 'Hae sää';
  }
  async function lookup(manual) {
    cancel();
    const id = generation;
    const params = query();
    if (!params.get('date') || !params.get('time') || (!params.get('place') && !(params.get('latitude') && params.get('longitude')))) {
      if (manual) status.textContent = 'Syötä päivämäärä, aloitusaika ja paikka. Reissun voi tallentaa ilman säähakua.';
      return;
    }
    const original = Object.fromEntries(fieldNames.map(name => [name, input(name).value]));
    button.disabled = true;
    button.textContent = 'Haetaan…';
    status.textContent = 'Haetaan säätietoja Ilmatieteen laitokselta… Voit tallentaa reissun myös ilman säätietoja.';
    controller = new AbortController();
    const currentController = controller;
    const timeout = setTimeout(() => currentController.abort(), 45000);
    try {
      const response = await fetch(button.dataset.url, {
        method: 'POST', headers: {'X-CSRFToken': input('csrfmiddlewaretoken').value},
        body: params, signal: currentController.signal
      });
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Säähaku epäonnistui. Yritä uudelleen.');
      const data = await response.json();
      if (id !== generation) return;
      if (!response.ok) throw new Error(data.error || 'Säähaku epäonnistui.');
      if (query().toString() !== params.toString()) return;
      let changed = 0;
      for (const name of fieldNames) {
        if (data.values[name] === undefined || input(name).value !== original[name] || (!manual && dirty.has(name))) continue;
        input(name).value = data.values[name];
        if (manual) dirty.delete(name);
        changed++;
      }
      form.dispatchEvent(new CustomEvent('weather-location', {detail: data.location}));
      updateCompass();
      if (changed) {
        input('weather_source').value = data.source;
        document.getElementById('weather-source').textContent = data.source;
      }
      const location = data.location ? 'Haettu paikka: ' + data.location.name + ' (' + data.location.latitude + ', ' + data.location.longitude + '). ' : '';
      status.textContent = location + data.source + '. Täytetty ' + changed + ' kenttää. Voit muokata arvoja.'
        + (data.missing.length ? ' Puuttuvat: ' + data.missing.join(', ') + '. Puuttuvia tietoja ei korvattu nollilla.' : '')
        + (!manual && dirty.size ? ' Käsin täyttämäsi kentät säilytettiin. Hae sää -painike päivittää myös ne.' : '');
    } catch (error) {
      if (id !== generation) return;
      status.textContent = (error.name === 'AbortError' ? 'Säähaun aikaraja ylittyi.' : error.message)
        + ' Voit tallentaa reissun ilman säätietoja tai täyttää tiedot käsin.';
    } finally {
      clearTimeout(timeout);
      if (id === generation) { button.disabled = false; button.textContent = 'Hae sää'; }
    }
  }
  button.addEventListener('click', () => lookup(true));
  for (const name of ['date', 'start_time', 'location', 'weather_place', 'latitude', 'longitude']) {
    input(name).addEventListener('change', () => {
      cancel();

      if (auto.checked) timer = setTimeout(() => lookup(false), 800);
    });
  }
  auto.addEventListener('change', () => { cancel(); if (auto.checked) timer = setTimeout(() => lookup(false), 800); });
  form.addEventListener('submit', cancel);
  updateCompass();
})();

