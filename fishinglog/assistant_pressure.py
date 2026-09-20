"""Pressure changes from adjacent points of ONE place's existing forecast.

Thresholds and the small stability preference are conservative UI heuristics,
not a claim that a pressure direction predicts fishing success.
"""
from datetime import datetime
from math import isfinite
from django.utils import timezone


def pressure_trends(samples):
    points = {}
    for sample in samples:
        try:
            target = sample['target']
            moment = target if isinstance(target, datetime) else datetime.fromisoformat(target)
            if timezone.is_naive(moment):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        try:
            value = float(sample.get('values', {}).get('air_pressure'))
            if not isfinite(value) or value <= 0:
                value = None
        except (TypeError, ValueError):
            value = None
        # Duplicate timestamps cannot supply independent trend evidence.
        points[moment] = None if moment in points else value
    ordered = sorted(points)
    results = {}
    for index, moment in enumerate(ordered):
        value = points[moment]
        row = {'value': value, 'trend': None, 'strength': None, 'adjustment': 0}
        results[moment] = row
        if value is None:
            continue
        neighbors = ([ordered[index-1]] if index else []) + ([ordered[index+1]] if index+1 < len(ordered) else [])
        for neighbor in neighbors:
            hours = abs((moment-neighbor).total_seconds()) / 3600
            # Never interpolate over a missing point or an extended forecast gap.
            if points[neighbor] is None or not .5 <= hours <= 6:
                continue
            before, after = sorted((moment, neighbor))
            delta = points[after] - points[before]
            rate = delta / hours
            # Normalize to a 3h interval; rounding noise below 0.5 hPa is stable.
            change = abs(rate)*3
            trend = 'stable' if change <= .5 else 'rising' if rate > 0 else 'falling'
            strength = 'stable' if trend == 'stable' else 'strong' if change >= 2 else 'moderate'
            row.update(trend=trend, strength=strength, delta_hpa=round(delta, 2),
                       hours=round(hours, 2), rate_hpa_per_hour=round(rate, 3),
                       start=before.isoformat(), end=after.isoformat(),
                       comparison='previous' if neighbor < moment else 'next',
                       adjustment=round(max(-.2, .1-min(change, 3)*.1), 3))
            break
    return results


def describe_pressure(pressure):
    if pressure.get('value') is None:
        return 'Ilmanpaineesta ei ole ennustetietoa. Painetrendiä ei voida arvioida.'
    def number(value):
        return f'{value:g}'.replace('.', ',')
    text = f"Ilmanpaine {number(pressure['value'])} hPa"
    trend = pressure.get('trend')
    if trend is None:
        return text + '. Painetrendiin ei ole riittävästi peräkkäisiä ennustepisteitä.'
    text += ', ' + {'rising': 'nousussa', 'falling': 'laskussa', 'stable': 'pysynyt melko vakaana'}[trend]
    if pressure['comparison'] == 'next' and trend == 'stable':
        text = text.replace('pysynyt melko vakaana', 'ennusteen mukaan melko vakaa')
    interval = 'edeltävän' if pressure['comparison'] == 'previous' else 'seuraavan'
    delta = pressure['delta_hpa']
    signed = ('+' if delta > 0 else '') + number(delta)
    text += f" (ennuste {interval} {number(pressure['hours'])} h ajalta: {signed} hPa)"
    if pressure['strength'] == 'strong':
        text += ' · voimakas muutos'
    return text + '.'
