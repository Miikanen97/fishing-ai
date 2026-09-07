from .test_helpers import LoggedInMixin
from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch, MagicMock
from xml.sax.saxutils import escape
import requests
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import TripForm, WeatherLookupForm
from .models import Trip
from .weather import (OBS_QUERY, FORECAST_QUERY, NoWeatherData, WeatherError,
                      download, fetch_weather, parse_response)

TARGET = datetime(2024, 6, 1, 9, tzinfo=utc.utc)


def xml_data(rows, name='Testiasema', position='61.87 28.88'):
    # Same namespaces and structure as FMI's timevaluepair response.
    members = []
    for param, value, moment in rows:
        members.append(f"""
        <omso:PointTimeSeriesObservation>
          <om:observedProperty xlink:href="https://opendata.fmi.fi/meta?param={param}&amp;language=eng"/>
          <om:featureOfInterest><gml:Point><gml:name>{escape(name)}</gml:name><gml:pos>{position}</gml:pos></gml:Point></om:featureOfInterest>
          <om:result><wml:MeasurementTimeseries><wml:point><wml:MeasurementTVP>
            <wml:time>{moment.isoformat()}</wml:time><wml:value>{value}</wml:value>
          </wml:MeasurementTVP></wml:point></wml:MeasurementTimeseries></om:result>
        </omso:PointTimeSeriesObservation>""")
    return ('<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:omso="http://inspire.ec.europa.eu/schemas/omso/3.0" '
            'xmlns:om="http://www.opengis.net/om/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" '
            'xmlns:wml="http://www.opengis.net/waterml/2.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
            + ''.join(members) + '</wfs:FeatureCollection>').encode()


OBS = xml_data([(p, v, TARGET) for p, v in [('t2m', '-2.5'), ('ws_10min', '0'), ('wd_10min', '360'),
                                                       ('p_sea', '1012.3'), ('n_man', '4'), ('r_1h', '0'), ('wg_10min', '5.2')]])
FORECAST = xml_data([(p, v, TARGET) for p, v in [('Temperature', '12.34'), ('WindSpeedMS', '5.5'),
    ('WindDirection', '180'), ('Pressure', '1010'), ('TotalCloudCover', '75'), ('Precipitation1h', '1.2'), ('WindGust', '8.5')]])


class WeatherServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        resolver = patch('fishinglog.weather.resolve_place', return_value={'name': 'Testipaikka', 'latitude': 61.87, 'longitude': 28.88, 'source': 'FMI'})
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_observations_units_and_zero_values(self):
        result = parse_response(OBS, TARGET, False)
        self.assertEqual(result['values']['air_temperature'], '-2.5')
        self.assertEqual(result['values']['cloud_cover'], '50.0')
        self.assertEqual(result['values']['precipitation'], '0.0')
        self.assertEqual(result['values']['wind_speed'], '0.0')
        self.assertEqual(result['missing'], [])
        self.assertIn('01.06.2024 12:00', result['source'])
        self.assertEqual(result['kind'], 'observation')

    def test_forecast_mapping_and_rounding(self):
        result = parse_response(FORECAST, TARGET, True)
        self.assertEqual(result['values']['cloud_cover'], '75.0')
        self.assertEqual(result['values']['air_temperature'], '12.3')
        self.assertEqual(result['values']['precipitation'], '1.2')
        self.assertEqual(result['kind'], 'forecast')

    def test_missing_sentinels_and_out_of_range_values(self):
        xml = xml_data([(p, v, TARGET) for p, v in [('t2m', 'NaN'), ('n_man', '9'), ('r_1h', '-1'),
                        ('wd_10min', '999'), ('p_sea', 'INF'), ('ws_10min', '2')]])
        result = parse_response(xml, TARGET, False)
        self.assertEqual(result['values'], {'wind_speed': '2.0'})
        self.assertEqual(len(result['missing']), 6)

    def test_closest_time_and_hour_limit(self):
        xml = xml_data([('t2m', '99', TARGET - timedelta(hours=2)), ('t2m', '3', TARGET + timedelta(minutes=10)),
                        ('t2m', '4', TARGET - timedelta(minutes=5))])
        self.assertEqual(parse_response(xml, TARGET, False)['values']['air_temperature'], '4.0')
        with self.assertRaises(NoWeatherData):
            parse_response(xml_data([('t2m', '9', TARGET - timedelta(hours=2))]), TARGET, False)

    def test_xml_and_exception_errors(self):
        for xml in [b'not XML', b'<ExceptionReport/>', b'<!DOCTYPE x [<!ENTITY a "bad">]><x>&a;</x>']:
            with self.subTest(xml=xml), self.assertRaises(WeatherError):
                parse_response(xml, TARGET, False)
        with self.assertRaises(NoWeatherData):
            parse_response(xml_data([]), TARGET, False)

    @patch('fishinglog.weather.download', return_value=OBS)
    def test_historical_query_utc_and_cache(self, mock):
        target = TARGET.replace(microsecond=123)
        fetch_weather('Helsinki', target, now=TARGET + timedelta(days=100))
        params = mock.call_args.args[0]
        self.assertEqual(params['storedquery_id'], OBS_QUERY)
        self.assertEqual(params['starttime'], '2024-06-01T08:00:00+00:00')
        self.assertIn('bbox', params)
        fetch_weather('Helsinki', target, now=TARGET + timedelta(days=100))
        self.assertEqual(mock.call_count, 1)

    @patch('fishinglog.weather.download', return_value=FORECAST)
    def test_future_query_and_coordinates(self, mock):
        fetch_weather('61.87, 28.88', TARGET, now=TARGET - timedelta(days=1))
        self.assertEqual(mock.call_args.args[0]['storedquery_id'], FORECAST_QUERY)
        self.assertEqual(mock.call_args.args[0]['latlon'], '61.87,28.88')

    @patch('fishinglog.weather.download', return_value=OBS)
    def test_observation_coordinates_use_bbox(self, mock):
        result = fetch_weather('61.87,28.88', TARGET, now=TARGET + timedelta(days=1))
        self.assertIn('bbox', mock.call_args.args[0])
        self.assertNotIn('latlon', mock.call_args.args[0])
        self.assertEqual(len(result['values']), 10)
        with self.assertRaises(NoWeatherData):
            parse_response(OBS, TARGET, False, coords=(65, 25))

    @patch('fishinglog.weather.download', side_effect=[xml_data([]), FORECAST])
    def test_recent_missing_observation_uses_labelled_forecast(self, mock):
        result = fetch_weather('Helsinki', TARGET, now=TARGET + timedelta(minutes=30))
        self.assertEqual(result['kind'], 'forecast')
        self.assertEqual(mock.call_count, 2)

    @patch('fishinglog.weather.download', return_value=xml_data([]))
    def test_no_forecast_fallback_for_old_history(self, mock):
        with self.assertRaises(NoWeatherData):
            fetch_weather('Helsinki', TARGET, now=TARGET + timedelta(days=30))
        self.assertEqual(mock.call_count, 1)

    @patch('fishinglog.weather.download', return_value=xml_data([]))
    def test_outside_forecast_range(self, mock):
        with self.assertRaises(NoWeatherData):
            fetch_weather('Helsinki', TARGET, now=TARGET - timedelta(days=30))

    @patch('fishinglog.weather.requests.get', side_effect=requests.Timeout)
    def test_network_timeout(self, mock):
        with self.assertRaisesMessage(WeatherError, 'yhteyttä'):
            download({})

    @patch('fishinglog.weather.requests.get')
    def test_http_error_and_response_size(self, mock):
        response = mock.return_value.__enter__.return_value
        response.status_code = 503
        with self.assertRaises(WeatherError):
            download({})
        response.status_code = 200
        response.iter_content.return_value = [b'x' * 2_000_001]
        with self.assertRaisesMessage(WeatherError, 'suuri'):
            download({})

    def test_bad_coordinates(self):
        with self.assertRaises(WeatherError):
            fetch_weather('91,25', TARGET)

    def test_dst_and_local_time_validation(self):
        form = WeatherLookupForm(dict(date='2024-06-01', time='12:00', place='Helsinki'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['target'], TARGET)
        for date in ['2024-03-31', '2024-10-27']:
            form = WeatherLookupForm(dict(date=date, time='03:30', place='Helsinki'))
            self.assertFalse(form.is_valid())


class WeatherViewTests(LoggedInMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('fishinglog:weather_lookup')
        self.data = dict(date='2024-06-01', time='12:00', place='Helsinki')

    @patch('fishinglog.views.fetch_weather')
    def test_endpoint_fills_values_without_saving_trip(self, mock):
        mock.return_value = parse_response(OBS, TARGET, False)
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['values']['cloud_cover'], '50.0')
        self.assertEqual(Trip.objects.count(), 0)
        self.assertEqual(mock.call_args.args, ('Helsinki', TARGET))

    @patch('fishinglog.views.fetch_weather')
    def test_bad_input_no_network_call(self, mock):
        for data in [{}, {**self.data, 'date': 'wrong'}, {**self.data, 'place': 'x' * 201}]:
            self.assertEqual(self.client.post(self.url, data).status_code, 400)
        mock.assert_not_called()

    @patch('fishinglog.views.fetch_weather', side_effect=WeatherError('Sääpalvelu ei vastaa.'))
    def test_failure_json(self, mock):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 422)
        self.assertIn('error', response.json())

    def test_post_only_and_csrf(self):
        from django.test import Client
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, self.data).status_code, 403)

    def test_weather_controls_only_on_trip_form(self):
        response = self.client.get(reverse('fishinglog:trip_create'))
        self.assertContains(response, 'id="fetch-weather"')
        self.assertContains(response, 'weather.js')
        self.assertContains(response, 'type="hidden" name="weather_source"')

    def test_new_fields_save_and_remain_editable(self):
        data = dict(date='2024-06-01', lake='Saimaa', location='Savonlinna', start_time='12:00', end_time='18:00', fishing_method='Jiggaus',
                    wind_speed='4.1', wind_direction='270', air_pressure='1012', cloud_cover='50', precipitation='0.2', weather_source='FMI test')
        response = self.client.post(reverse('fishinglog:trip_create'), data)
        trip = Trip.objects.get()
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.wind_speed, Decimal('4.1'))
        self.assertContains(self.client.get(trip.get_absolute_url()), 'FMI test')
        response = self.client.post(reverse('fishinglog:trip_update', args=[trip.pk]), {**data, 'wind_speed': '7.5'})
        trip.refresh_from_db()
        self.assertEqual(trip.wind_speed, Decimal('7.5'))
        for field, value in [('wind_speed', '-1'), ('wind_direction', '361'), ('cloud_cover', '101'), ('precipitation', '-1')]:
            form = TripForm({**data, field: value})
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)


class WeatherExtensionTests(LoggedInMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_gust_description_and_compass(self):
        from .weather import compass
        result = parse_response(OBS, TARGET, False)
        self.assertEqual(result['values']['wind_gust'], '5.2')
        self.assertIn('Puolipilvistä', result['values']['weather'])
        self.assertEqual(result['wind_compass'], 'pohjoinen')
        for number, expected in [(90, 'itä'), (180, 'etelä'), (270, 'länsi'), (315, 'luode'), (None, '')]:
            self.assertEqual(compass(number), expected)

    def test_kyyvesi_offline_location(self):
        from .weather import resolve_place
        with patch('fishinglog.weather.requests.get') as request:
            place = resolve_place('Kyyvesi')
        request.assert_not_called()
        self.assertEqual(place['latitude'], 61.99757)
        self.assertEqual(place['longitude'], 27.16802)

    @patch('fishinglog.weather.requests.get')
    def test_named_place_lookup_cached_and_correct(self, mock):
        import json
        from .weather import resolve_place
        response = mock.return_value.__enter__.return_value
        response.status_code = 200
        for name, lat, lon in [('Kangasniemi', 61.99357, 26.64785), ('Jyväskylä', 62.24147, 25.72088)]:
            response.iter_content.return_value = [json.dumps([{'name': name, 'latitude': lat, 'longitude': lon}]).encode()]
            location = resolve_place(name)
            self.assertEqual(location['latitude'], lat)
            self.assertEqual(location['longitude'], lon)
            self.assertEqual(resolve_place(name), location)
        self.assertEqual(mock.call_count, 2)

    @patch('fishinglog.weather.requests.get')
    def test_location_response_failures(self, mock):
        from .weather import resolve_place
        response = mock.return_value.__enter__.return_value
        response.status_code = 400
        with self.assertRaisesMessage(WeatherError, 'Paikkaa ei löytynyt'):
            resolve_place('tuntematon')
        response.status_code = 200
        for payload in [b'not JSON', b'[]', b'{}', b'[{"name":"bad","latitude":999,"longitude":20}]']:
            response.iter_content.return_value = [payload]
            with self.assertRaises(WeatherError):
                resolve_place('bad')
        mock.side_effect = requests.ConnectionError
        with self.assertRaises(WeatherError):
            resolve_place('offline')

    @patch('fishinglog.weather.download', return_value=OBS)
    def test_target_coordinates_are_not_station_coordinates(self, mock):
        mock.return_value = OBS.replace(b'61.87 28.88', b'62.00 27.10')
        result = fetch_weather('Kyyvesi', TARGET, now=TARGET + timedelta(days=1))
        self.assertEqual(result['values']['weather_latitude'], '61.99757')
        self.assertEqual(result['values']['weather_longitude'], '27.16802')
        self.assertIn('62.00000, 27.10000', result['source'])

    def test_coordinates_and_gust_save_and_display(self):
        data = dict(date='2024-06-01', lake='Kyyvesi', location='Kyyvesi', start_time='12:00', end_time='18:00',
                    fishing_method='Jiggaus', latitude='61.99757', longitude='27.16802', wind_gust='7.5', wind_direction='270')
        response = self.client.post(reverse('fishinglog:trip_create'), data)
        trip = Trip.objects.get()
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.latitude, Decimal('61.99757'))
        self.assertEqual(trip.wind_gust, Decimal('7.5'))
        self.assertContains(self.client.get(trip.get_absolute_url()), 'länsi')

    def test_trip_still_saves_after_weather_failure(self):
        with patch('fishinglog.views.fetch_weather', side_effect=WeatherError('Verkkovirhe')):
            response = self.client.post(reverse('fishinglog:weather_lookup'), dict(date='2024-06-01',time='12:00',place='Kyyvesi'))
            self.assertEqual(response.status_code, 422)
        data = dict(date='2024-06-01', lake='Kyyvesi', location='Kyyvesi', start_time='12:00', end_time='18:00', fishing_method='Jiggaus')
        self.assertEqual(self.client.post(reverse('fishinglog:trip_create'), data).status_code, 302)
        trip = Trip.objects.get()
        self.assertIsNone(trip.wind_gust)
        self.assertIsNone(trip.air_temperature)

    def test_optional_coordinates_and_invalid_ranges(self):
        data = dict(date='2024-06-01', lake='Kyyvesi', location='Kyyvesi', start_time='12:00', end_time='18:00', fishing_method='Jiggaus')
        self.assertTrue(TripForm(data).is_valid())
        for field, value in [('latitude','91'),('longitude','181'),('wind_gust','-1')]:
            form = TripForm({**data,field:value})
            self.assertFalse(form.is_valid())
            self.assertIn(field,form.errors)

