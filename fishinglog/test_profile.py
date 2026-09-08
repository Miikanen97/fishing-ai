from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import FishingProfile
from .home_weather import upcoming_weather
from .weather import WeatherError, NoWeatherData


class ProfileTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('profile-owner')
        self.other = get_user_model().objects.create_user('other-profile')
        self.client.force_login(self.user)
        self.url = reverse('fishinglog:settings')

    def test_login_and_csrf_required(self):
        self.client.logout()
        for method in ('get', 'post'):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'default_weather_place':'Kyyvesi'}).status_code, 403)

    @patch('fishinglog.profile_views.resolve_place', return_value={'latitude':61.99757,'longitude':27.16802})
    def test_save_reload_and_owner_forgery(self, resolve):
        FishingProfile.objects.create(user=self.other, default_weather_place='Private lake')
        response = self.client.post(self.url, {'default_weather_place':'Kyyvesi','user':self.other.pk,'latitude':'0'})
        self.assertRedirects(response,self.url)
        profile = FishingProfile.objects.get(user=self.user)
        self.assertEqual(profile.latitude, Decimal('61.99757'))
        self.assertEqual(FishingProfile.objects.get(user=self.other).default_weather_place,'Private lake')
        self.assertContains(self.client.get(self.url), 'Kyyvesi')
        self.assertNotContains(self.client.get(self.url), 'Private lake')
        self.client.post(self.url, {'default_weather_place':''})
        profile.refresh_from_db()
        self.assertEqual(profile.default_weather_place,'')
        self.assertIsNone(profile.latitude)
        resolve.assert_called_once()

    @patch('fishinglog.profile_views.resolve_place', side_effect=WeatherError('offline'))
    def test_failed_resolution_preserves_name_but_clears_stale_coordinates(self, resolve):
        FishingProfile.objects.create(user=self.user,default_weather_place='Old',latitude=62,longitude=26)
        self.assertEqual(self.client.post(self.url,{'default_weather_place':'New'}).status_code,302)
        profile = FishingProfile.objects.get(user=self.user)
        self.assertEqual(profile.default_weather_place,'New')
        self.assertIsNone(profile.latitude)
        self.assertIsNone(profile.longitude)

    @patch('fishinglog.home_weather.upcoming_weather')
    def test_home_without_place_never_fetches_weather(self, fetch):
        FishingProfile.objects.create(user=self.other,default_weather_place='Private lake')
        self.assertContains(self.client.get('/'),'Aseta oma kalastuspaikka')
        self.assertNotContains(self.client.get('/'),'Private lake')
        self.client.logout()
        self.assertEqual(self.client.get('/').status_code,200)
        fetch.assert_not_called()

    @patch('fishinglog.assistant.call_openai')
    @patch('fishinglog.home_weather.upcoming_weather')
    def test_home_weather_is_automatic_and_never_calls_ai(self, fetch, ai):
        FishingProfile.objects.create(user=self.user,default_weather_place='Kyyvesi',latitude=62,longitude=26)
        fetch.return_value={'rows':[{'target':timezone.now(),'values':{'air_temperature':'15','wind_speed':'3','wind_gust':'6','air_pressure':'1010','precipitation':'0','cloud_cover':'50'}}], 'fetched_at':timezone.now(),'missing_count':0}
        response=self.client.get('/')
        self.assertContains(response,'Kyyvesi')
        self.assertContains(response,'1010 hPa')
        fetch.assert_called_once_with('62.00000,26.00000')
        ai.assert_not_called()
        fetch.side_effect=WeatherError('offline')
        self.assertContains(self.client.get('/'),'Sääennustetta ei saatu')
        ai.assert_not_called()

    @patch('fishinglog.home_weather.weather.resolve_place', return_value={'latitude':62,'longitude':26})
    @patch('fishinglog.home_weather.weather.download', return_value=b'<xml/>')
    @patch('fishinglog.home_weather.weather.parse_response', return_value={'values':{'air_temperature':'15'}})
    def test_forecast_range_cache_and_partial_results(self, parse, download, resolve):
        first = upcoming_weather('Kyyvesi')
        self.assertEqual(len(first['rows']),16)
        self.assertGreater(first['rows'][0]['target'],timezone.now())
        self.assertLess(first['rows'][-1]['target'],timezone.now()+timedelta(hours=48))
        self.assertEqual(upcoming_weather('Kyyvesi'),first)
        download.assert_called_once()
        cache.clear()
        parse.side_effect = [NoWeatherData('missing')] + [{'values':{}}]*15
        self.assertEqual(upcoming_weather('Kyyvesi')['missing_count'],1)
        cache.clear()
        parse.side_effect=NoWeatherData('missing')
        with self.assertRaises(NoWeatherData): upcoming_weather('Kyyvesi')
