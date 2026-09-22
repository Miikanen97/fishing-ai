"""Bounded, cached public-name fallback. Never pass user records to this module."""
import hashlib
import json
import math
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from .assistant_places import forms, normalize
from .models import GeocodingGate, PublicGeocodingCache
from .weather import distance


class AmbiguousGeocoding(ValueError):
    """Provider returned multiple distinct matching locations."""


def lookup(name, area=None):
    region = {k: area[k] for k in ('latitude', 'longitude')} if area else None
    key = hashlib.sha256(json.dumps([normalize(name), region], sort_keys=True).encode()).hexdigest()
    now = timezone.now()
    try:
        cached = PublicGeocodingCache.objects.filter(pk=key, expires_at__gt=now).first()
        if cached:
            if cached.result == {'ambiguous': True}:
                raise AmbiguousGeocoding('Multiple public locations')
            return cached.result
        gate, _ = GeocodingGate.objects.get_or_create(pk=1, defaults={'next_allowed': now})
        delay = (gate.next_allowed - now).total_seconds()
        if 0 < delay <= 1.1:
            time.sleep(delay + 0.01)  # One bounded cooldown, never a retry loop.
            now = timezone.now()
        # A 30-second lease exceeds the bounded connect/read timeout. No retries,
        # no queues: concurrent requests fail closed rather than exceed OSM limits.
        lease = now + timedelta(seconds=30)
        if not GeocodingGate.objects.filter(pk=1, next_allowed__lte=now).update(next_allowed=lease):
            return None
    except DatabaseError:
        return None
    params = {'q': name, 'format': 'jsonv2', 'countrycodes': 'fi',
              'addressdetails': 1, 'limit': 5}
    if area:
        lat, lon = area['latitude'], area['longitude']
        params.update(viewbox=f'{lon-2},{lat+1},{lon+2},{lat-1}', bounded=1)
    result = None
    cacheable = False
    started = time.monotonic()
    try:
        with requests.get(settings.NOMINATIM_URL, params=params,
                          headers={'User-Agent': settings.NOMINATIM_USER_AGENT},
                          timeout=(3, 5), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                return None
            body = bytearray()
            for chunk in response.iter_content(8192):
                body.extend(chunk)
                if len(body) > 100000 or time.monotonic()-started > 15:
                    return None
            rows = json.loads(body)
        if not isinstance(rows, list):
            return None
        found = []
        for row in rows[:5]:
            if row.get('address', {}).get('country_code') != 'fi':
                continue
            canonical = row.get('name', '')
            if normalize(name) not in forms(canonical):
                continue
            lat, lon = float(row['lat']), float(row['lon'])
            if not (math.isfinite(lat) and math.isfinite(lon) and 59 <= lat <= 71 and 19 <= lon <= 32):
                continue
            if area and distance((lat, lon), (area['latitude'], area['longitude'])) > 100:
                continue
            if not any(distance((lat, lon), (r['latitude'], r['longitude'])) < 1 for r in found):
                found.append({'name': canonical[:100], 'latitude': lat, 'longitude': lon, 'osm': True})
        result = found[0] if len(found) == 1 else {'ambiguous': True} if len(found) > 1 else None
        cacheable = True
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        pass
    finally:
        try:
            GeocodingGate.objects.filter(pk=1, next_allowed=lease).update(next_allowed=timezone.now()+timedelta(seconds=1))
            if cacheable:
                PublicGeocodingCache.objects.update_or_create(pk=key, defaults={
                    'result': result, 'expires_at': timezone.now()+timedelta(hours=24 if result and result != {'ambiguous': True} else 1)})
        except DatabaseError:
            pass
    if result == {'ambiguous': True}:
        raise AmbiguousGeocoding('Multiple public locations')
    return result
