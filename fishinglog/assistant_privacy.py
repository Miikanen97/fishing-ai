"""Outbound copy only: internal weather/scoring data remains untouched."""
import re

COORDINATE_PAIR = re.compile(r"(?<![\w.])-?\d{1,2}\.\d+\s*[,;]\s*-?\d{1,3}\.\d+(?![\w.])")
PRIVATE_FIELDS = frozenset(('latitude', 'longitude', 'weather_latitude', 'weather_longitude',
                            'lat', 'lon', 'latlon', 'coordinates', 'coords', 'source', 'weather_source'))


def private_payload(payload, notes_spot=None):
    """No stored coordinates; notes require explicit single-place consent per request.

    Notes share a 2,000-character budget and remain untrusted user content.
    Coordinate-like pairs in text are also removed (not a general PII detector).
    """
    remaining = 2000

    def clean(value, permitted=False):
        nonlocal remaining
        if isinstance(value, dict):
            if 'spot_id' in value:
                permitted = notes_spot is not None and value['spot_id'] == notes_spot
            result = {}
            for key, item in value.items():
                if key in PRIVATE_FIELDS:
                    continue
                if key == 'notes':
                    if not permitted or not isinstance(item, str) or not remaining:
                        continue
                    item = item[:min(250, remaining)]
                    remaining -= len(item)
                result[key] = clean(item, permitted)
            return result
        if isinstance(value, (list, tuple)):
            return [clean(item, permitted) for item in value]
        if isinstance(value, str):
            return COORDINATE_PAIR.sub('[tarkka sijainti poistettu]', value)
        return value

    result = clean(payload)
    result['notes_policy'] = ('Vain erikseen sallittu yhden paikan otos, enintään 2000 merkkiä; ei täydellinen historia.'
                              if notes_spot is not None else 'Muistiinpanoja ei lähetetty. Älä väitä lukeneesi niitä.')
    return result
