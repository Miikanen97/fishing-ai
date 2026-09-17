import json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import FishingSpot, Trip, Catch
from .test_catch_batch import trip_data
from .test_assistant import ANSWER
from . import assistant as ai


class AssistantSpotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('owner')
        self.other = get_user_model().objects.create_user('other')
        self.spot = FishingSpot.objects.create(user=self.user, name='Oma selkä', latitude=62, longitude=26)
        self.secret = FishingSpot.objects.create(user=self.other, name='SECRET_SPOT', latitude=63, longitude=27)
        self.trip = Trip.objects.create(owner=self.user, fishing_spot=self.spot, **trip_data())
        Catch.objects.create(trip=self.trip, species='Kuha', length='0.5', weight='1.2', time='10:00', notes='Oma havainto')
        foreign = Trip.objects.create(owner=self.other, fishing_spot=self.spot, **trip_data())
        Catch.objects.create(trip=foreign, species='SECRET_FISH', time='10:00')

    def test_history_links_and_privacy(self):
        context = ai.spots_for(self.user, '')
        self.assertEqual(len(context['places']), 1)
        spot = context['places'][0]
        self.assertEqual(spot['total_trips'], 1)
        self.assertTrue(spot['limited_history'])
        fish = spot['history'][0]['catches'][0]
        self.assertEqual(fish['species'], 'Kuha')
        self.assertEqual(str(fish['length']), '0.500')
        self.assertNotIn('SECRET', json.dumps(context, default=str))

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([{'target': 'tomorrow'}], []))
    def test_comparison_bounded_and_one_call(self, forecast, api):
        for i in range(5):
            FishingSpot.objects.create(user=self.user, name=f'Paikka {i}', latitude=62+i, longitude=26)
        result = ai.advise(self.user, 'Mihin kannattaisi mennä huomenna kalaan?')
        self.assertEqual(forecast.call_count, 3)
        api.assert_called_once()
        payload = api.call_args.args[1]
        self.assertEqual(len(payload['spot_forecasts']), 3)
        self.assertNotIn('SECRET', json.dumps(payload, default=str))
        self.assertIn('historiaa on vähän', result['answer']['uncertainty'])

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', side_effect=ai.weather.WeatherError('offline'))
    def test_missing_forecasts_safe(self, forecast, api):
        result = ai.advise(self.user, 'Mihin huomenna?')
        self.assertIsNone(result['answer']['score'])
        self.assertTrue(result['warning'])
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window')
    def test_history_only_and_places_without_history(self, forecast, api):
        empty = FishingSpot.objects.create(user=self.user, name='Uusi')
        ai.advise(self.user, 'Vertaa kalapaikkojen reissuja')
        forecast.assert_not_called()
        payload = api.call_args.args[1]
        row = next(p for p in payload['saved_spots']['places'] if p['spot_id'] == empty.pk)
        self.assertEqual(row['history'], [])
        self.assertTrue(row['limited_history'])

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([{'target': 'tomorrow'}], []))
    def test_named_spot_uses_coordinates(self, forecast, api):
        ai.advise(self.user, 'Kannattaako huomenna mennä Oma selkä?')
        self.assertEqual(forecast.call_args.args[0], '62.00000,26.00000')
        self.assertEqual(forecast.call_args.args[1], 'tomorrow')
        api.assert_called_once()

    def test_tomorrow_uses_shared_forecast_and_local_date(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        from django.core.cache import cache
        cache.clear()
        now = timezone.make_aware(datetime(2026, 9, 10, 10))
        with patch('fishinglog.home_weather.timezone.now', return_value=now), patch('fishinglog.weather.download', return_value=b'xml') as download, patch('fishinglog.weather.parse_response', return_value={'values': {}}), patch('fishinglog.weather.requests.get') as network:
            samples, _ = ai.forecast_window('62.12345,26.54321', 'tomorrow', now)
            self.assertTrue(samples)
            self.assertTrue(all(datetime.fromisoformat(row['target']).date() == (now + timedelta(days=1)).date() for row in samples))
            self.assertEqual(download.call_args.args[0]['latlon'], '62.12345,26.54321')
            ai.forecast_window('62.12345,26.54321', 'tomorrow', now)
            download.assert_called_once()
            network.assert_not_called()

    def test_safe_failure_logging(self):
        with self.assertLogs(ai.logger, level='DEBUG') as logs:
            ai.log_weather_failure(ai.weather.WeatherError('SECRET_KEY PRIVATE_LOCATION'))
        self.assertNotIn('SECRET', str(logs.output))
        self.assertNotIn('PRIVATE', str(logs.output))
        self.assertIn('service_or_location_error', str(logs.output))

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([{'target': 'tomorrow'}], []))
    def test_comparison_falls_back_to_spot_name(self, forecast, api):
        self.spot.latitude = self.spot.longitude = None
        self.spot.name = 'Jämsä'
        self.spot.save()
        result = ai.advise(self.user, 'Mihin huomenna kalaan?')
        forecast.assert_called_once()
        self.assertEqual(forecast.call_args.args[:2], ('Jämsä', 'tomorrow'))
        self.assertFalse(result['warning'])
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window')
    def test_empty_spot_skips_weather(self, forecast, api):
        self.spot.latitude = self.spot.longitude = None
        self.spot.name = ''
        self.spot.save()
        result = ai.advise(self.user, 'Mihin huomenna?')
        forecast.assert_not_called()
        self.assertTrue(result['warning'])
        api.assert_called_once()

    def test_named_tomorrow_resolves_then_downloads(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        from django.core.cache import cache
        cache.clear()
        now = timezone.make_aware(datetime(2026, 9, 10, 10))
        with patch('fishinglog.home_weather.timezone.now', return_value=now), patch('fishinglog.weather.resolve_place', return_value={'latitude':61.86, 'longitude':25.19}) as resolve, patch('fishinglog.weather.download', return_value=b'xml') as download, patch('fishinglog.weather.parse_response', return_value={'values': {}}):
            samples, _ = ai.forecast_window('Jämsä', 'tomorrow', now)
            resolve.assert_called_once_with('Jämsä')
            self.assertEqual(download.call_args.args[0]['latlon'], '61.86,25.19')
            self.assertTrue(samples)
            self.assertTrue(all(datetime.fromisoformat(row['target']).date() == (now + timedelta(days=1)).date() for row in samples))

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([{'target': 'tomorrow'}], []))
    def test_trip_name_works_without_saved_spot(self, forecast, api):
        self.trip.fishing_spot = None
        self.trip.latitude = self.trip.longitude = None
        self.trip.lake = 'Jämsä'
        self.trip.weather_place = ''
        self.trip.save()
        ai.advise(self.user, 'Kannattaako huomenna kalaan?')
        self.assertEqual(forecast.call_args.args[0], 'Jämsä')
        api.assert_called_once()


class AssistantQueryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('batch-history')

    def test_grouped_history_keeps_top_eight_per_trip_with_three_queries(self):
        for i in range(3):
            trip = Trip.objects.create(owner=self.user, **trip_data())
            for count in range(1, 10):
                Catch.objects.bulk_create([Catch(trip=trip, species=f'Laji {count}', time='12:00') for _ in range(count)])
        with self.assertNumQueries(3):
            data = ai.history_for(self.user)
        self.assertEqual(data['total_trips'], 3)
        self.assertEqual(data['included_trips'], 3)
        for trip in data['recent_trips']:
            self.assertEqual(trip['fish_count'], 45)
            self.assertEqual([g['count'] for g in trip['catch_groups']], list(range(9, 1, -1)))
            self.assertTrue(all(set(g) == {'species','lure_name','lure_color','depth','time','count'} for g in trip['catch_groups']))

    def test_spot_samples_keep_counts_order_and_limits_in_four_queries(self):
        for i in range(12):
            spot = FishingSpot.objects.create(user=self.user, name=f'Ranta {i}')
            trips = [Trip.objects.create(owner=self.user, fishing_spot=spot, **trip_data()) for _ in range(10)]
            Catch.objects.bulk_create([Catch(trip=trips[-1], species=f'Kala {j}', time='12:00') for j in range(10)])
        with self.assertNumQueries(4):
            data = ai.spots_for(self.user, '')
        self.assertEqual(data['total_places'], 12)
        self.assertEqual(len(data['places']), 10)
        for spot in data['places']:
            self.assertEqual(spot['total_trips'], 10)
            self.assertLessEqual(spot['included_trips'], 8)
            self.assertTrue(spot['history'])
            first = spot['history'][0]
            self.assertEqual(first['catch_count'], 10)
            self.assertEqual([c['species'] for c in first['catches']], [f'Kala {j}' for j in range(8)])
