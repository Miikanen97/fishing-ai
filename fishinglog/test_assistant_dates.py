from datetime import datetime, timedelta, timezone as utc
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from . import assistant as ai
from .assistant_dates import weekday_request, calendar_date
from .assistant_location import context
from .models import FishingSpot
from .test_assistant import ANSWER

TZ=ZoneInfo('Europe/Helsinki')
NOW=datetime(2026,9,22,12,tzinfo=TZ)  # Tuesday; production code contains no fixed dates.

class WeekdayTests(SimpleTestCase):
    def test_all_seven_days_and_capitalization(self):
        for index,word in enumerate(('maanantaina','tiistaina','keskiviikkona','torstaina','perjantaina','lauantaina','sunnuntaina')):
            expected=NOW.date()+timedelta(days=(index-NOW.weekday())%7)
            for variant in (word,word.upper(),word.capitalize()):
                with self.subTest(word=variant):
                    target,clean=weekday_request(f'millainen sää vaherissa {variant}',NOW)
                    self.assertEqual(target,expected)
                    self.assertNotIn(variant,clean)
                    self.assertEqual(ai.interpret_question(f'Vaheri {variant}',now=NOW)['period'],expected.isoformat())

    def test_same_day_next_week_and_modifiers(self):
        thursday=NOW+timedelta(days=2)
        for word in ('torstai','torstaina','tulevana torstaina','tänä torstaina'):
            self.assertEqual(weekday_request(word,thursday)[0],thursday.date())
        self.assertEqual(weekday_request('ensi torstaina',thursday)[0],thursday.date()+timedelta(days=7))
        self.assertEqual(weekday_request('ensi torstaina',NOW)[0],thursday.date()+timedelta(days=7))
        self.assertEqual(weekday_request('torstaina',thursday.replace(hour=23,minute=45))[0],thursday.date()+timedelta(days=7))

    def test_finland_day_boundary_year_and_dst(self):
        sunday_utc=datetime(2026,9,20,22,tzinfo=utc.utc)
        self.assertEqual(weekday_request('maanantaina',sunday_utc)[0].isoformat(),'2026-09-21')
        self.assertEqual(weekday_request('maanantaina',datetime(2026,12,31,12,tzinfo=TZ))[0].isoformat(),'2027-01-04')
        self.assertEqual(weekday_request('sunnuntaina',datetime(2026,10,24,12,tzinfo=TZ))[0].isoformat(),'2026-10-25')

    def test_ambiguous_days_request_clarification(self):
        with self.assertRaises(ValueError):
            weekday_request('maanantaina vai torstaina',NOW)
        self.assertIsNone(calendar_date('2026-99-99'))
        self.assertIsNone(calendar_date('tomorrow'))

    def test_public_session_preserves_exact_date(self):
        stored={'name':'Vaheri','latitude':61.8,'longitude':25.3,'period':'2026-09-24','updated':NOW.timestamp()}
        self.assertEqual(context(stored,NOW)['period'],'2026-09-24')

class ForecastDateTests(SimpleTestCase):
    @patch('fishinglog.assistant.weather.parse_response',return_value={'values':{}})
    @patch('fishinglog.assistant.weather.download',return_value=b'xml')
    @patch('fishinglog.assistant.weather.resolve_place',return_value={'latitude':61.8,'longitude':25.3})
    def test_exact_day_query_and_dst_offsets(self,resolve,download,parse):
        samples,missing=ai.forecast_window('61.8,25.3','2026-10-25',datetime(2026,10,24,12,tzinfo=TZ))
        self.assertTrue(all(datetime.fromisoformat(row['target']).date().isoformat()=='2026-10-25' for row in samples))
        query=download.call_args.args[0]
        self.assertTrue(query['starttime'].startswith('2026-10-24T21:00'))
        self.assertTrue(query['endtime'].startswith('2026-10-25T21:00'))
        download.assert_called_once()

    @patch('fishinglog.assistant.weather.parse_response',side_effect=ai.weather.NoWeatherData('no forecast points'))
    @patch('fishinglog.assistant.weather.download',return_value=b'empty')
    @patch('fishinglog.assistant.weather.resolve_place',return_value={'latitude':61.8,'longitude':25.3})
    def test_valid_date_beyond_available_forecast_is_no_data(self,resolve,download,parse):
        with self.assertRaises(ai.weather.NoWeatherData):
            ai.forecast_window('61.8,25.3','2026-10-01',NOW)
        self.assertTrue(download.call_args.args[0]['starttime'].startswith('2026-09-30T21:00'))

class WeekdayIntegrationTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('weekday-owner')
        self.client.force_login(self.user)

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.assistant_location.resolve',return_value={'name':'Vaheri','latitude':61.8,'longitude':25.3})
    @patch('fishinglog.assistant.timezone.localtime')
    def test_followup_and_next_week_strip_temporal_words_before_place_lookup(self,localtime,resolve,forecast,api):
        localtime.side_effect=lambda value=None: value if value is not None else NOW
        for question,expected in (('Entäs Vaherissa torstaina?','2026-09-24'),('Vaheri ensi torstaina','2026-10-01')):
            response=self.client.post('/avustaja/',{'question':question})
            self.assertEqual(response.status_code,200)
            self.assertNotContains(response,'Tarkenna kysymystä:')
            self.assertEqual(forecast.call_args.args[:2],('61.8,25.3',expected))
            self.assertEqual(api.call_args.args[1]['plan']['period'],expected)
        self.assertEqual(api.call_count,2)
        self.assertTrue(all('torstai' not in call.args[0] for call in resolve.call_args_list))

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',side_effect=ai.weather.NoWeatherData('outside model horizon'))
    @patch('fishinglog.assistant.timezone.localtime')
    def test_unavailable_date_is_explicit_and_own_coordinates_remain_primary(self,localtime,forecast,api):
        localtime.side_effect=lambda value=None: value if value is not None else NOW
        FishingSpot.objects.create(user=self.user,name='Vaheri',latitude=62,longitude=26)
        with patch('fishinglog.geocoding.lookup_all') as nomi:
            response=self.client.post('/avustaja/',{'question':'Vaheri ensi torstaina'})
        self.assertContains(response,'01.10.2026')
        self.assertContains(response,'Sääennustetta ei ole vielä saatavilla kyseiselle päivälle')
        self.assertNotContains(response,'Tarkenna kysymystä:')
        self.assertEqual(forecast.call_args.args[:2],('62.00000,26.00000','2026-10-01'))
        nomi.assert_not_called()
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',side_effect=ai.weather.WeatherError('connection problem'))
    @patch('fishinglog.assistant.timezone.localtime')
    def test_network_error_is_not_claimed_to_be_forecast_horizon(self,localtime,forecast,api):
        localtime.side_effect=lambda value=None: value if value is not None else NOW
        FishingSpot.objects.create(user=self.user,name='Vaheri',latitude=62,longitude=26)
        response=self.client.post('/avustaja/',{'question':'Vaheri torstaina'})
        self.assertContains(response,'Sääpalvelusta ei saatu tietoja')
        self.assertNotContains(response,'ei ole vielä saatavilla kyseiselle päivälle')
