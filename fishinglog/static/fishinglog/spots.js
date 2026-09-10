(() => {
  const node = document.getElementById('spots-map');
  if (!node) return;
  const status = document.getElementById('spots-status');
  if (!window.L) { status.textContent = 'Karttaa ei saatu ladattua. Voit silti syöttää koordinaatit lomakkeeseen.'; return; }
  const map = L.map(node).setView([62, 26], 6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  const lat = document.getElementById('id_latitude'), lon = document.getElementById('id_longitude');
  let selected, locationMarker;
  function setPoint(a, b) {
    lat.value = a.toFixed(5); lon.value = b.toFixed(5);
    if (!selected) {
      selected = L.marker([a,b], {draggable:true}).addTo(map);
      selected.on('dragend', () => { const point = selected.getLatLng(); setPoint(point.lat, point.lng); });
    } else selected.setLatLng([a,b]);
    status.textContent = 'Valittu piste: ' + lat.value + ', ' + lon.value;
  }
  function readPoint() {
    const a = Number(lat.value.replace(',', '.')), b = Number(lon.value.replace(',', '.'));
    if (!lat.value.trim() || !lon.value.trim() || !Number.isFinite(a) || !Number.isFinite(b) || Math.abs(a)>90 || Math.abs(b)>180) return;
    setPoint(a,b); map.setView([a,b], 13);
  }
  const items = JSON.parse(document.getElementById('spots-data').textContent);
  const points = [], savedMarkers = [];
  items.forEach(item => {
    const point = [Number(item.latitude), Number(item.longitude)]; points.push(point);
    const popup = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = item.name; popup.appendChild(title);
    const notes = document.createElement('p'); notes.className = 'spot-popup-notes'; notes.textContent = item.notes; popup.appendChild(notes);
    const coords = document.createElement('p'); coords.textContent = item.latitude + ', ' + item.longitude; popup.appendChild(coords);
    [['Muokkaa',item.edit_url],['Poista',item.delete_url]].forEach(([label,url]) => {
      const link = document.createElement('a'); link.textContent = label; link.href = url; link.className = 'me-3'; popup.appendChild(link);
    });
    savedMarkers.push(L.marker(point).addTo(map).bindPopup(popup));
  });
  if (points.length) map.fitBounds(points, {padding:[35,35], maxZoom:13});
  readPoint();
  lat.addEventListener('change', readPoint); lon.addEventListener('change', readPoint);
  map.on('click', event => {
    setPoint(event.latlng.lat, event.latlng.lng);
    document.getElementById('spot-editor').open = true;
  });
  document.querySelectorAll('.spot-focus').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      const index = Number(link.dataset.spotIndex);
      map.setView(points[index], 15);
      savedMarkers[index].openPopup();
      node.scrollIntoView({behavior:'smooth', block:'center'});
    });
  });
  document.getElementById('spots-locate').addEventListener('click', function () {
    if (!navigator.geolocation) { status.textContent = 'Selain ei tue sijaintihakua.'; return; }
    this.disabled = true; status.textContent = 'Haetaan sijaintia…';
    navigator.geolocation.getCurrentPosition(position => {
      this.disabled = false;
      const point = [position.coords.latitude, position.coords.longitude];
      if (locationMarker) locationMarker.setLatLng(point);
      else locationMarker = L.circleMarker(point, {radius:8,color:'#1769aa'}).addTo(map);
      map.setView(point,14); status.textContent = 'Sijaintisi näkyy sinisenä. Valitse tallennettava paikka napauttamalla karttaa.';
    }, () => { this.disabled = false; status.textContent = 'Sijaintia ei saatu. Voit jatkaa valitsemalla paikan kartalta.'; },
    {enableHighAccuracy:true,timeout:10000,maximumAge:60000});
  });
})();
