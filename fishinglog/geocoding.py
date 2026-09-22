"""Bounded, cached public-name fallback. Never pass user records to this module."""
import hashlib
import json
import math
import logging
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


def report(service, count, reason, area=False):
    logging.getLogger('fishinglog.places').warning(
        'place_resolution service=%s candidates=%d reason=%s area_context=%s',
        service, count, reason, bool(area))


def lookup(name, area=None):
    rows = lookup_all(name, area)
    if len(rows) > 1:
        raise AmbiguousGeocoding('Multiple public locations')
    return rows[0] if rows else None


def lookup_all(name, area=None):
    region = {k: area[k] for k in ('latitude', 'longitude')} if area else None
    key = hashlib.sha256(json.dumps(['hierarchy-v2', normalize(name), region], sort_keys=True).encode()).hexdigest()
    now = timezone.now()
    try:
        cached = PublicGeocodingCache.objects.filter(pk=key, expires_at__gt=now).first()
        if cached:
            report('nominatim', len(cached.result or []), 'cache', area)
            return cached.result or []
        gate, _ = GeocodingGate.objects.get_or_create(pk=1, defaults={'next_allowed': now})
        delay = (gate.next_allowed - now).total_seconds()
        if 0 < delay <= 1.1:
            time.sleep(delay + 0.01)  # One bounded cooldown, never a retry loop.
            now = timezone.now()
        # A 30-second lease exceeds the bounded connect/read timeout. No retries,
        # no queues: concurrent requests fail closed rather than exceed OSM limits.
        lease = now + timedelta(seconds=30)
        if not GeocodingGate.objects.filter(pk=1, next_allowed__lte=now).update(next_allowed=lease):
            report('nominatim', 0, 'rate_limited', area)
            return []
    except DatabaseError:
        report('nominatim', 0, 'database_error', area)
        return []
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
                report('nominatim', 0, 'http_' + str(response.status_code), area)
                return []
            body = bytearray()
            for chunk in response.iter_content(8192):
                body.extend(chunk)
                if len(body) > 100000 or time.monotonic()-started > 15:
                    return []
            rows = json.loads(body)
        if not isinstance(rows, list):
            return []
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
            if not any(distance((lat, lon), (r['latitude'], r['longitude'])) < 1 and r.get('type') == row.get('addresstype', row.get('type', '')) for r in found):
                entry = {'name': canonical[:100], 'latitude': lat, 'longitude': lon, 'osm': True,
                         'type': str(row.get('addresstype', row.get('type', '')))[:40],
                         'address': {k: str(v)[:100] for k,v in row.get('address', {}).items()
                                     if k in ('town','city','village','hamlet','suburb','municipality','county','state','lake','region')}}
                try:
                    box = [float(v) for v in row.get('boundingbox', [])]
                    if len(box) == 4 and all(math.isfinite(v) for v in box) and 59 <= box[0] <= box[1] <= 71 and 19 <= box[2] <= box[3] <= 32:
                        entry['bbox'] = box
                except (TypeError, ValueError):
                    pass
                found.append(entry)
        result = found
        report('nominatim', len(found), 'candidates_retained' if found else 'no_matching_candidates', area)
        cacheable = True
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        report('nominatim', 0, type(exc).__name__, area)
    finally:
        try:
            GeocodingGate.objects.filter(pk=1, next_allowed=lease).update(next_allowed=timezone.now()+timedelta(seconds=1))
            if cacheable:
                PublicGeocodingCache.objects.update_or_create(pk=key, defaults={
                    'result': result, 'expires_at': timezone.now()+timedelta(hours=24 if result else 1)})
        except DatabaseError:
            report('nominatim', 0, 'cache_write_error', area)
    return result or []
