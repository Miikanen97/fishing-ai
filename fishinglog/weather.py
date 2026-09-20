"""FMI WFS observations and official point forecasts. All timestamps are aware."""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt, isfinite
import re
import logging
from functools import wraps
from time import monotonic
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import ParseError

import requests
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.core.cache import cache
from django.utils import timezone

ENDPOINT = 'https://opendata.fmi.fi/wfs'
OBS_QUERY = 'fmi::observations::weather::timevaluepair'
FORECAST_QUERY = 'fmi::forecast::edited::weather::scandinavia::point::timevaluepair'
FIELDS = {
    'air_temperature': 'Ilman lämpötila',
    'wind_speed': 'Tuulen nopeus',
    'wind_direction': 'Tuulen suunta',
    'air_pressure': 'Ilmanpaine',
    'cloud_cover': 'Pilvisyys',
    'precipitation': 'Sade',
}
OBS_PARAMS = dict(zip(['t2m', 'ws_10min', 'wd_10min', 'p_sea', 'n_man', 'r_1h'], FIELDS))
FORECAST_PARAMS = dict(zip(['temperature', 'windspeedms', 'winddirection', 'pressure', 'totalcloudcover', 'precipitation1h'], FIELDS))
FIELDS['wind_gust'] = 'Tuulenpuuskat'
OBS_PARAMS['wg_10min'] = 'wind_gust'
FORECAST_PARAMS['windgust'] = 'wind_gust'
NS = {
    'omso': 'http://inspire.ec.europa.eu/schemas/omso/3.0',
    'om': 'http://www.opengis.net/om/2.0',
    'gml': 'http://www.opengis.net/gml/3.2',
    'wml': 'http://www.opengis.net/waterml/2.0',
}
MAX_BYTES = 2_000_000


class WeatherError(Exception):
    pass


class NoWeatherData(WeatherError):
    pass


# Only fixed diagnostic categories are emitted; never exception messages/tracebacks.
logger = logging.getLogger('fishinglog.fmi')
FMI_CODES = frozenset({'InvalidParameterValue', 'MissingParameterValue', 'OperationNotSupported',
    'OperationProcessingFailed', 'NoApplicableCode', 'OptionNotSupported', 'VersionNegotiationFailed',
    'InvalidValue', 'ParsingFailed', 'OperationParsingFailed'})


class DiagnosticXML(bytes):
    """Preserve the bytes API while carrying request metadata into the parser."""
    pass


def log_failure(exc, stage='forecast', duration_ms=None, http_status=None, fmi_code=None):
    if getattr(exc, '_fmi_logged', False):
        return
    cause = exc.__cause__ or exc
    kind = 'no_data' if isinstance(exc, NoWeatherData) else 'service_error'
    for cls, label in [(requests.exceptions.SSLError, 'tls_error'),
                       (requests.Timeout, 'timeout'), (requests.ConnectionError, 'connection_error'),
                       (requests.HTTPError, 'http_error'), (requests.RequestException, 'request_error'),
                       (ParseError, 'xml_error'), (DefusedXmlException, 'xml_error'),
                       (ValueError, 'invalid_data'), (KeyError, 'invalid_data'),
                       (IndexError, 'invalid_data'), (TypeError, 'invalid_data')]:
        if isinstance(cause, cls):
            kind = label
            break
    status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
    if status is None:
        status = getattr(exc, '_fmi_status', None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    if status is not None and status >= 400:
        kind = 'http_error'
    code = fmi_code if fmi_code in FMI_CODES else getattr(exc, '_fmi_code', None)
    code = code if code in FMI_CODES else None
    if code:
        kind = 'fmi_exception'
    elapsed = round(max(0, duration_ms), 1) if type(duration_ms) in (int, float) else None
    logger.warning('FMI failure stage=%s type=%s http_status=%s fmi_code=%s duration_ms=%s',
        stage if stage in {'location', 'wfs_request', 'parse', 'forecast'} else 'forecast',
        kind, status, code, elapsed)
    exc._fmi_logged = True


def diagnostic(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            started = monotonic()
            try:
                result = function(*args, **kwargs)
                if stage == 'wfs_request':
                    result.duration_ms = (monotonic() - started) * 1000
                return result
            except WeatherError as exc:
                xml = args[0] if stage == 'parse' and args else None
                log_failure(exc, stage, getattr(xml, 'duration_ms', (monotonic() - started) * 1000),
                    getattr(xml, 'http_status', None))
                raise
        return wrapped
    return decorate


def compass(value):
    if value is None:
        return ''
    directions = ['pohjoinen', 'koillinen', 'itä', 'kaakko', 'etelä', 'lounas', 'länsi', 'luode']
    return directions[int((float(value) % 360 + 22.5) // 45) % 8]


def describe_weather(values):
    parts = []
    if 'cloud_cover' in values:
        cloud = Decimal(values['cloud_cover'])
        parts.append('Selkeää' if cloud <= 20 else 'Puolipilvistä' if cloud <= 70 else 'Pilvistä')
    if 'precipitation' in values:
        rain = Decimal(values['precipitation'])
        parts.append(f'Sadetta {rain} mm tunnissa' if rain > 0 else 'Ei mitattavaa sadetta tunnin aikana')
    return 'Yhteenveto sääarvoista: ' + '; '.join(parts) if parts else ''


@diagnostic('location')
def resolve_place(place):
    coords = coordinates(place)
    if coords:
        return {'name': place, 'latitude': coords[0], 'longitude': coords[1], 'source': 'Käyttäjän koordinaatit'}
    # Lake representative point, not the fishing spot. Offline gazetteer fallback.
    # Source: https://www.openstreetmap.org/relation/303354 (ODbL).
    if place.strip().casefold() == 'kyyvesi':
        return {'name': 'Kyyvesi (järven edustava piste)', 'latitude': 61.99757, 'longitude': 27.16802,
                'source': '© OpenStreetMap contributors'}
    key = 'fmi-place:' + sha256(place.casefold().encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        with requests.get('https://opendata.fmi.fi/timeseries', params={'place': place, 'param': 'name,latitude,longitude',
                          'format': 'json', 'timesteps': 1}, timeout=(5, 10), stream=True,
                          headers={'User-Agent': 'FishingLog/1.0'}, allow_redirects=False) as response:
            if response.status_code == 400:
                error = WeatherError('Paikkaa ei löytynyt. Kokeile kunnan nimeä tai koordinaatteja (esim. 61.99, 26.65).')
                error._fmi_status = response.status_code
                raise error
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(8192):
                content.extend(chunk)
                if len(content) > 100000:
                    error = WeatherError('Paikkapalvelun vastaus oli liian suuri. Tarkenna paikkaa.')
                    error._fmi_status = response.status_code
                    raise error
            import json
            data = json.loads(content)
            row = data[0]
            lat, lon = float(row['latitude']), float(row['longitude'])
            if not (isfinite(lat) and isfinite(lon) and -90 < lat < 90 and -180 <= lon <= 180):
                raise ValueError
            result = {'name': str(row['name'])[:200], 'latitude': lat, 'longitude': lon, 'source': 'Ilmatieteen laitos'}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        error = WeatherError('Paikan sijaintia ei saatu haettua. Tarkista paikka ja verkkoyhteys. Voit tallentaa reissun ilman säätietoja.')
        error._fmi_status = getattr(locals().get('response'), 'status_code', None)
        raise error from exc
    cache.set(key, result, 86400)
    return result


def coordinates(place):
    """Return a coordinate pair, or None for a place name."""
    if not re.fullmatch(r'\s*[+-]?[\d.]+\s*,\s*[+-]?[\d.]+\s*', place):
        return None
    try:
        lat, lon = (float(part) for part in place.split(','))
        if not (-90 < lat < 90 and -180 <= lon <= 180):
            raise ValueError
        return lat, lon
    except ValueError:
        raise WeatherError('Tarkista koordinaatit: leveysaste, pituusaste (esim. 61.87, 28.88).')


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371 * 2 * asin(min(1, sqrt(h)))


@diagnostic('wfs_request')
def download(params):
    try:
        with requests.get(ENDPOINT, params=params, timeout=(5, 15), stream=True,
                          headers={'User-Agent': 'FishingLog/1.0'}, allow_redirects=False) as response:
            # WFS commonly returns an XML ExceptionReport with HTTP 400.
            if response.status_code not in (200, 400):
                error = WeatherError('Ilmatieteen laitoksen sääpalvelu ei vastaa. Yritä myöhemmin.')
                error._fmi_status = response.status_code
                raise error
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > MAX_BYTES:
                    error = WeatherError('Sääpalvelun vastaus oli liian suuri. Tarkenna paikkaa.')
                    error._fmi_status = response.status_code
                    raise error
                chunks.append(chunk)
            result = DiagnosticXML(b''.join(chunks))
            result.http_status = response.status_code
            return result
    except requests.RequestException as exc:
        error = WeatherError('Sääpalveluun ei saatu yhteyttä. Tarkista verkkoyhteys ja yritä uudelleen.')
        error._fmi_status = getattr(locals().get('response'), 'status_code', None)
        raise error from exc


@diagnostic('parse')
def parse_response(xml, target, forecast, coords=None):
    try:
        root = ElementTree.fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise WeatherError('Sääpalvelu palautti virheellisen vastauksen. Yritä myöhemmin.') from exc
    if root.tag.endswith('ExceptionReport'):
        error = WeatherError('FMI ei voinut käsitellä hakua. Tarkista paikannimi tai käytä koordinaatteja; myös ajankohdan data voi puuttua.')
        error._fmi_code = next((node.get('exceptionCode') for node in root.iter() if node.get('exceptionCode') in FMI_CODES), None)
        raise error
    mapping = FORECAST_PARAMS if forecast else OBS_PARAMS
    stations = {}
    for series in root.findall('.//omso:PointTimeSeriesObservation', NS):
        prop = series.find('om:observedProperty', NS)
        if prop is None:
            continue
        parameter = parse_qs(urlparse(prop.get('{http://www.w3.org/1999/xlink}href', '')).query).get('param', [''])[0].lower()
        if parameter not in mapping:
            continue
        point = series.find('.//gml:Point', NS)
        if point is None:
            continue
        name = point.findtext('gml:name', default='FMI:n mittauspiste', namespaces=NS)
        try:
            position = tuple(float(x) for x in point.findtext('gml:pos', '', NS).split()[:2])
            if len(position) != 2 or not all(isfinite(x) for x in position):
                continue
        except ValueError:
            continue
        if coords and not forecast and distance(coords, position) > 50:
            continue
        key = (name, position)
        station = stations.setdefault(key, {})
        for tvp in series.findall('.//wml:MeasurementTVP', NS):
            try:
                moment = datetime.fromisoformat(tvp.findtext('wml:time', '', NS).replace('Z', '+00:00'))
                value = Decimal(tvp.findtext('wml:value', '', NS))
                if moment.tzinfo is None or not value.is_finite() or abs(moment-target) > timedelta(hours=1):
                    continue
                if parameter == 'n_man':
                    if not 0 <= value <= 8:  # 9 = sky obscured, not 112.5% cloud
                        continue
                    value *= Decimal('12.5')
                field = mapping[parameter]
                if field != 'air_temperature' and value < 0:
                    continue
                if field == 'cloud_cover' and value > 100 or field == 'wind_direction' and value > 360:
                    continue
                # Match model capacity; sentinel values must never reach the form.
                if field == 'air_temperature' and abs(value) >= 1000 or abs(value) >= 1000000:
                    continue
                candidate = (abs(moment-target), moment, value.quantize(Decimal('0.1')))
                if field not in station or candidate[:2] < station[field][:2]:
                    station[field] = candidate
            except (ValueError, InvalidOperation, TypeError):
                continue
    stations = {key: values for key, values in stations.items() if values}
    if not stations:
        raise NoWeatherData('Ajankohdan läheltä ei löytynyt säätietoja. Tarkista paikka tai täytä tiedot käsin.')
    # Keep a single station: do not silently combine different observation sites.
    key = min(stations, key=lambda key: (distance(coords, key[1]) if coords else 0, -len(stations[key])))
    values = stations[key]
    kind = 'Ennuste' if forecast else 'Havainto'
    times = sorted(set(timezone.localtime(row[1]).strftime('%d.%m.%Y %H:%M') for row in values.values()))
    source = f'Ilmatieteen laitos · {kind} · {key[0]} ({key[1][0]:.5f}, {key[1][1]:.5f}) · ' + ', '.join(times) + ' (Suomen aika)'
    output = {field: str(row[2]) for field, row in values.items()}
    description = describe_weather(output)
    if description:
        output['weather'] = description
    return {
        'values': output,
        'wind_compass': compass(output.get('wind_direction')),
        'source': source,
        'kind': 'forecast' if forecast else 'observation',
        'missing': [label for field, label in FIELDS.items() if field not in values],
        'times': {field: timezone.localtime(row[1]).strftime('%d.%m.%Y %H:%M') for field, row in values.items()},
    }


def fetch_weather(place, target, now=None):
    now = now or timezone.now()
    coordinates(place)  # Validate explicit coordinates before any network call.
    forecast = target > now
    key = 'fmi-v3:' + sha256(f'{place.lower()}|{target.isoformat()}|{forecast}'.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    resolved = resolve_place(place)
    coords = (resolved['latitude'], resolved['longitude'])

    def query(is_forecast):
        mapping = FORECAST_PARAMS if is_forecast else OBS_PARAMS
        try:
            start = target - timedelta(hours=1)
            end = target + timedelta(hours=1)
        except OverflowError as exc:
            raise WeatherError('Päivämäärä ei kuulu sääpalvelun tukemaan aikaväliin.') from exc
        if not is_forecast:
            end = min(end, now)
        params = dict(service='WFS', version='2.0.0', request='getFeature',
                      storedquery_id=FORECAST_QUERY if is_forecast else OBS_QUERY,
                      parameters=','.join(mapping), starttime=start.astimezone(dt_timezone.utc).isoformat(timespec='seconds'),
                      endtime=end.astimezone(dt_timezone.utc).isoformat(timespec='seconds'), timestep=10 if not is_forecast else 60)
        if coords:
            lat, lon = coords
            if is_forecast:
                params['latlon'] = f'{lat},{lon}'
            else:
                lat_span = 50 / 111
                lon_span = min(180, 50 / (111 * max(.01, cos(radians(lat)))))
                params['bbox'] = f'{max(-180,lon-lon_span)},{max(-90,lat-lat_span)},{min(180,lon+lon_span)},{min(90,lat+lat_span)}'
        else:
            params['place'] = place
            if not is_forecast:
                params['maxlocations'] = 1
        return parse_response(download(params), target, is_forecast, coords)

    try:
        result = query(forecast)
    except NoWeatherData:
        # Recent observations can be delayed; never replace old history with a forecast.
        if not forecast and now - target <= timedelta(hours=3):
            result = query(True)
        else:
            raise NoWeatherData('Säätietoja ei löytynyt tälle paikalle ja ajalle. Vanhojen havaintojen saatavuus riippuu asemasta; ennuste ulottuu yleensä noin 10 päivää eteenpäin.')
    result['location'] = resolved
    result['values']['weather_latitude'] = f"{coords[0]:.5f}"
    result['values']['weather_longitude'] = f"{coords[1]:.5f}"
    cache.set(key, result, 300)
    return result

