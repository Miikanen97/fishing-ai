(() => {
  const element = document.getElementById('fishing-map');
  if (!element) return;
  const status = document.getElementById('map-status');
  if (!window.L) { status.textContent = 'Karttaa ei saatu ladattua. Voit täyttää koordinaatit käsin.'; return; }
  const editable = element.dataset.editable === 'true';
  const form = editable ? element.closest('form') : null;
  const field = name => form.elements.namedItem(name);
  const read = (a, b) => {
    if (a === '' || b === '' || a == null || b == null) return null;
    const lat = Number(String(a).replace(',', '.')), lon = Number(String(b).replace(',', '.'));
    return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 ? [lat, lon] : null;
  };
  const current = () => editable ? read(field('latitude').value, field('longitude').value) : read(element.dataset.latitude, element.dataset.longitude);
  const initial = current();
  const weatherPoint = editable ? read(field('weather_latitude').value, field('weather_longitude').value) : null;
  const map = L.map(element, {scrollWheelZoom:false}).setView(initial || weatherPoint || [62, 26], initial ? 13 : weatherPoint ? 10 : 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom:19, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).on('tileerror', () => { status.textContent = 'Karttapohjaa ei saatu ladattua. Tarkista verkkoyhteys. Koordinaatit voi silti tallentaa.'; }).addTo(map);
  // Explicit Django static URLs also work with WhiteNoise manifest hashes.
  const markerIcon = L.icon({
    iconUrl: element.dataset.iconUrl, iconRetinaUrl: element.dataset.iconRetinaUrl,
    shadowUrl: element.dataset.shadowUrl,
    iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
    tooltipAnchor: [16, -28], shadowSize: [41, 41]
  });
  let marker, locationRequest = 0;
  function show(point, pan = true) {
    if (!point) {
      if (marker) { map.removeLayer(marker); marker = null; }
      status.textContent = 'Tarkkaa sijaintia ei ole valittu.';
      return;
    }
    if (!marker) {
      marker = L.marker(point, {icon:markerIcon, draggable:editable, title:'Kalastuspaikka', alt:'Kalastuspaikka'}).addTo(map);
      if (editable) marker.on('dragend', () => { const p=marker.getLatLng(); choose([p.lat,p.lng]); });
    } else marker.setLatLng(point);
    if (pan) map.panTo(point);
    status.textContent = 'Valittu kalastuspaikka: ' + point[0].toFixed(5) + ', ' + point[1].toFixed(5);
  }
  function choose(point) {
    locationRequest++;
    point = [Math.max(-90, Math.min(90, point[0])), ((point[1]+180)%360+360)%360-180];
    field('latitude').value = point[0].toFixed(5);
    field('longitude').value = point[1].toFixed(5);
    show(point);
    // Both values are set before notifying weather lookup and other listeners.
    field('latitude').dispatchEvent(new Event('change', {bubbles:true}));
    field('longitude').dispatchEvent(new Event('change', {bubbles:true}));
  }
  show(initial, false);
  if (!editable) return;
  map.on('click', event => choose([event.latlng.lat, event.latlng.lng]));
  for (const name of ['latitude','longitude']) field(name).addEventListener('change', () => { locationRequest++; show(current()); });
  form.addEventListener('weather-location', event => {
    // A weather result may center an unselected map, but must never create/move the fishing marker.
    if (!current() && event.detail) {
      const point = read(event.detail.latitude, event.detail.longitude);
      if (point) map.setView(point, 10);
    }
  });
  document.getElementById('clear-location').addEventListener('click', () => {
    locationRequest++;
    field('latitude').value = ''; field('longitude').value = ''; show(null);
    field('latitude').dispatchEvent(new Event('change', {bubbles:true}));
    field('longitude').dispatchEvent(new Event('change', {bubbles:true}));
  });
  document.getElementById('locate-me').addEventListener('click', () => {
    if (!navigator.geolocation) { status.textContent = 'Selaimesi ei tue paikannusta. Valitse paikka kartalta.'; return; }
    const request = ++locationRequest;
    status.textContent = 'Haetaan sijaintia. Salli paikannus selaimen kysyessä.';
    navigator.geolocation.getCurrentPosition(position => {
      if (request !== locationRequest) return;
      choose([position.coords.latitude, position.coords.longitude]);
      map.setView(current(), 15);
      status.textContent += ' Paikannuksen arvioitu tarkkuus ' + Math.round(position.coords.accuracy) + ' m.';
    }, error => {
      if (request !== locationRequest) return;
      status.textContent = error.code === 1 ? 'Sijaintilupaa ei annettu. Voit valita paikan kartalta.' : 'Sijaintia ei saatu haettua. Valitse paikka kartalta tai yritä uudelleen.';
    }, {enableHighAccuracy:true,timeout:15000,maximumAge:0});
  });
})();

