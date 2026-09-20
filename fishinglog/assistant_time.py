"""Conservative time guidance, computed locally from the existing forecast/history.

Weights are product heuristics, not biological probabilities. No network or DB calls.
Solar elevation approximation: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
"""
from calendar import isleap
from datetime import datetime, time
from math import asin, cos, sin, pi, radians, degrees, isfinite
import re
from django.utils import timezone
from .assistant_pressure import pressure_trends, describe_pressure


def light_at(moment, coords):
    if not coords:
        return 'unknown'
    lat, lon = map(float, coords)
    if not all(map(isfinite, (lat, lon))) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return 'unknown'
    local = timezone.localtime(moment)
    hour = local.hour + local.minute / 60
    g = 2 * pi / (366 if isleap(local.year) else 365) * (local.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eq = 229.18 * (.000075 + .001868*cos(g) - .032077*sin(g) - .014615*cos(2*g) - .040849*sin(2*g))
    dec = .006918 - .399912*cos(g) + .070257*sin(g) - .006758*cos(2*g) + .000907*sin(2*g) - .002697*cos(3*g) + .00148*sin(3*g)
    solar_minutes = hour*60 + eq + 4*lon - local.utcoffset().total_seconds()/60
    angle = radians(solar_minutes/4 - 180)
    elevation = degrees(asin(max(-1, min(1, sin(radians(lat))*sin(dec) + cos(radians(lat))*cos(dec)*cos(angle)))))
    return 'dark' if elevation < -6 else 'twilight' if elevation < 5 else 'daylight'


def period(hour):
    return 'night' if hour < 5 or hour >= 22 else 'morning' if hour < 10 else 'day' if hour < 16 else 'evening'


def method_key(value):
    value = value.casefold()
    return 'jiggaus' if 'jig' in value else 'uistelu' if 'uistel' in value else value


def evidence(history, plan, bucket):
    """Count distinct successful trips, not number of fish in one trip."""
    trips = set()
    for trip in history:
        if plan['method'] and method_key(trip.get('fishing_method', '')) != plan['method']:
            continue
        for catch in trip.get('catches', trip.get('catch_groups', [])):
            if plan['species'] and catch.get('species', '').casefold() != plan['species']:
                continue
            try:
                value = catch.get('time')
                hour = value.hour if isinstance(value, time) else time.fromisoformat(str(value)).hour
            except (TypeError, ValueError):
                continue
            if period(hour) == bucket:
                trips.add((str(trip.get('date')), str(trip.get('start_time'))))
    return len(trips)


def guidance(samples, coords, history, plan, now, name=''):
    pressures = pressure_trends(samples)
    rows = []
    for sample in samples:
        try:
            target = sample['target']
            moment = target if isinstance(target, datetime) else datetime.fromisoformat(target)
            if timezone.is_naive(moment) or moment < now:
                continue
            moment = timezone.localtime(moment)
        except (KeyError, TypeError, ValueError):
            continue
        light = light_at(moment, coords)
        bucket = period(moment.hour)
        support = evidence(history, plan, bucket)
        night = light == 'dark' or (light == 'unknown' and bucket == 'night')
        # An isolated catch or calmer wind is not enough to favor darkness.
        allowed = not night or (bool(plan['method'] or plan['species']) and support >= 2)
        time_score = -2 if night else 1
        if not night and (light == 'twilight' or bucket in ('morning', 'evening')):
            time_score += 1 if plan['method'] == 'jiggaus' else .5
        def value(field):
            try:
                number = float(sample.get('values', {}).get(field))
                return number if isfinite(number) and number >= 0 else None
            except (TypeError, ValueError):
                return None
        wind, gust, rain = value('wind_speed'), value('wind_gust'), value('precipitation')
        weather_score = -(min(wind, 15)/3 if wind is not None else 1)
        weather_score -= min(rain, 10)/5 if rain is not None else 0
        weather_score -= max(0, gust-8)/2 if gust is not None else 0
        pressure = pressures.get(moment, {'value': None, 'trend': None, 'strength': None, 'adjustment': 0})
        rows.append({'pressure': pressure, 'target': moment.isoformat(), 'place': name, 'light': light,
                     'period': bucket, 'supporting_trips': support, 'eligible': allowed,
                     'priority': round(time_score + min(support, 3)*2 + weather_score + pressure['adjustment'], 2)})
    return rows


def selected_time_rows(answer, rows):
    """Do not mix identical clock times from different dates or fishing spots."""
    text = answer.get('best_time', '')
    match = (re.search(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)', text)
             or re.search(r'(?<![\d.])([01]?\d|2[0-3])\.([0-5]\d)(?![\d.])', text))
    if not rows or not match:
        return []
    clock = f'{int(match[1]):02d}:{match[2]}'
    chosen = [row for row in rows if row['target'][11:16] == clock]
    named_places = {r['place'] for r in chosen if r['place'] and r['place'].casefold() in (answer.get('recommendation', '') + ' ' + text).casefold()}
    if len(named_places) == 1:
        chosen = [r for r in chosen if r['place'] in named_places]
    date_match = re.search(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)', text)
    if date_match:
        try:
            selected_date = datetime(int(date_match[3]), int(date_match[2]), int(date_match[1])).date()
        except ValueError:
            return []
        chosen = [r for r in chosen if datetime.fromisoformat(r['target']).date() == selected_date]
    return chosen


def pressure_summary(answer, rows):
    if not rows:
        return ''
    selected = selected_time_rows(answer, rows)
    if len(selected) != 1:
        return 'Painetrendiä ei voitu yhdistää yksiselitteisesti valittuun paikkaan ja ajankohtaan.'
    return describe_pressure(selected[0].get('pressure', {}))


def constrain_answer(answer, rows, plan):
    """Keep the model's eligible time; correct unsupported night selections locally."""
    if not plan['species'] and plan['period'] != 'history':
        answer['species'] = ''
    chosen = selected_time_rows(answer, rows)
    if not chosen or all(row['eligible'] for row in chosen):
        return
    eligible = [row for row in rows if row['eligible']]
    if not eligible:
        answer.update(best_time='Ei riittävästi perusteltuja ajankohtia', score=None,
                      recommendation='Ennusteen yöajoille ei löytynyt riittävää kalastusperustetta.')
        return
    best = max(eligible, key=lambda row: row['priority'])
    moment = datetime.fromisoformat(best['target'])
    answer['best_time'] = moment.strftime('%d.%m.%Y klo %H:%M') + (f" · {best['place']}" if best['place'] else '')
    answer['recommendation'] = 'Vaihtoehtoinen ajankohta on ' + answer['best_time'] + '. Ajan tarkennus ei yksin vahvista lähtösuositusta.'
    answer['rationale'] += '\nAjan tarkennus: yöajan pelkkä tyyni sää ei riittänyt perusteeksi. Aika korjattiin valoisuuden, kalastustavan, oman historian ja sääpisteiden yhteisarvion perusteella.'
