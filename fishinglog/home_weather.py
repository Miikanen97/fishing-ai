from datetime import timedelta, timezone as utc
from hashlib import sha256
from django.core.cache import cache
from django.utils import timezone
from .models import FishingProfile
from . import weather


def upcoming_weather(place):
    key = 'home-forecast-v1:' + sha256(place.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    now = timezone.now()
    first = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    targets = [first + timedelta(hours=offset) for offset in range(0, 48, 3)]
    location = weather.resolve_place(place)
    coords = (location['latitude'], location['longitude'])
    xml = weather.download(dict(service='WFS', version='2.0.0', request='getFeature',
        storedquery_id=weather.FORECAST_QUERY, parameters=','.join(weather.FORECAST_PARAMS), timestep=60,
        latlon=f'{coords[0]},{coords[1]}', starttime=targets[0].astimezone(utc.utc).isoformat(),
        endtime=targets[-1].astimezone(utc.utc).isoformat()))
    rows = []
    for target in targets:
        try:
            rows.append({'target': target, **weather.parse_response(xml, target, True, coords)})
        except weather.NoWeatherData:
            continue
    if not rows:
        raise weather.NoWeatherData('Ennustetta ei löytynyt.')
    result = {'rows': rows, 'fetched_at': now, 'missing_count': len(targets) - len(rows)}
    cache.set(key, result, 300)
    return result


def home_weather(user):
    profile = FishingProfile.objects.filter(user=user).first()
    result = {'weather_profile': profile}
    if profile and profile.default_weather_place:
        place = (f'{profile.latitude},{profile.longitude}' if profile.latitude is not None and profile.longitude is not None
                 else profile.default_weather_place)
        try:
            result['home_forecast'] = upcoming_weather(place)
        except weather.WeatherError:
            result['home_weather_error'] = 'Sääennustetta ei saatu juuri nyt. Yritä myöhemmin tai tarkista oletuspaikka asetuksista.'
    return result
