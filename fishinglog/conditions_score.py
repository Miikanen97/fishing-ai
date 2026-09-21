"""Deterministic, bounded product heuristics; not catch probabilities."""
from math import isfinite, floor
from .assistant_pressure import describe_pressure

BASE = 6.0
# All adjustments are deliberately small and independent of personal history.
LIMIT = 1.0


def evaluate(sample, row, plan, relevant_trips=0):
    factors = []
    def number(key, low, high):
        try:
            value = float(sample.get('values', {}).get(key))
            return value if isfinite(value) and low <= value <= high else None
        except (TypeError, ValueError):
            return None
    def add(label, value, delta, unit=''):
        delta = max(-LIMIT, min(LIMIT, delta)) if value is not None else 0
        factors.append({'label': label, 'value': delta,
                        'impact': f'{delta:+.2f}'.replace('.', ','),
                        'direction': 'Nostaa' if delta > 0 else 'Laskee' if delta < 0 else 'Neutraali',
                        'detail': f'{value} {unit}'.strip() if value is not None else 'Ei tietoa; ei pistevaikutusta'})
    wind = number('wind_speed', 0, 100)
    gust = number('wind_gust', 0, 150)
    rain = number('precipitation', 0, 500)
    temp = number('air_temperature', -70, 60)
    cloud = number('cloud_cover', 0, 100)
    pressure = number('air_pressure', 800, 1100)
    add('Tuuli', wind, .75 if wind is not None and wind <= 5 else -.5 if wind is not None and wind <= 9 else -1, 'm/s')
    add('Puuskat', gust, -.5 if gust is not None and gust > 10 else 0, 'm/s')
    add('Sade', rain, .5 if rain == 0 else 0 if rain is not None and rain <= 1 else -.75, 'mm/h')
    add('Ilman lämpötila', temp, -.75 if temp is not None and (temp < 0 or temp > 30) else .25, '°C (ei veden lämpötila)')
    add('Pilvisyys', cloud, .25 if cloud is not None and 30 <= cloud <= 90 else 0, '%')
    # Absolute pressure has no defensible generic direction; show explicitly neutral.
    add('Ilmanpaine', pressure, 0, 'hPa; taso yksin on neutraali')
    trend = row.get('pressure', {})
    add('Painetrendi', trend.get('trend'), trend.get('adjustment', 0))
    factors[-1]['detail'] = describe_pressure(trend)
    light = row.get('light', 'unknown')
    add('Valoisuus', None if light == 'unknown' else light, -.5 if light == 'dark' else .5)
    factors[-1]['detail'] = {'unknown': 'Valoisuus ei tiedossa', 'dark': 'Pimeä', 'twilight': 'Hämärä', 'daylight': 'Valoisa'}[light]
    timing = row.get('period') in ('morning', 'evening') or light == 'twilight'
    add('Kalastustapa ja vuorokaudenaika', plan.get('method') or None,
        .25 if plan.get('method') == 'jiggaus' and timing else 0)
    # Optional, small twilight preference; absent species is exactly neutral.
    add('Kohdekala', plan.get('species') or None,
        .25 if plan.get('species') == 'kuha' and light == 'twilight' else 0)
    weather_count = sum(v is not None for v in (wind, rain, temp, cloud, pressure))
    available = weather_count >= 3 and wind is not None
    raw = BASE + sum(f['value'] for f in factors)
    score = max(1, min(10, floor(raw + .5))) if available else None
    confidence = 'Korkea' if relevant_trips >= 10 and weather_count == 5 and light != 'unknown' and trend.get('trend') else 'Kohtalainen' if relevant_trips >= 5 and weather_count >= 4 else 'Matala'
    return {'available': available, 'score': score, 'total': round(raw, 2), 'base': BASE,
            'factors': factors, 'confidence': confidence, 'relevant_trips': relevant_trips,
            'weather_count': weather_count, 'place': row['place'], 'target': row['target']}
