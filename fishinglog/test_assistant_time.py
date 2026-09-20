from datetime import datetime
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from .assistant_time import guidance, constrain_answer, light_at
from . import assistant as ai
from .test_assistant import ANSWER


def moment(day, hour, month=9):
    return timezone.make_aware(datetime(2026, month, day, hour))


def samples():
    return [{'target': moment(21, h).isoformat(), 'values': {'wind_speed': wind, 'precipitation': '0'}}
            for h, wind in [(3, '0.1'), (9, '2'), (15, '3')]]


def history(species='Kuha', hour='03:00'):
    return [{'date': f'2026-09-{day}', 'start_time': '01:00', 'fishing_method': 'Jigaus',
             'catches': [{'species': species, 'time': hour}]} for day in (10, 11)]


class TimeGuidanceTests(SimpleTestCase):
    plan = {'method': 'jiggaus', 'species': '', 'period': 'tomorrow'}

    def rows(self, past=(), species=''):
        return guidance(samples(), (61.99757, 27.16802), past, {**self.plan, 'species': species}, moment(20, 12))

    def test_calm_night_is_not_best_for_unspecified_jigging(self):
        rows = self.rows()
        self.assertFalse(rows[0]['eligible'])
        answer = {**ANSWER, 'best_time': '21.09.2026 klo 03:00'}
        constrain_answer(answer, rows, self.plan)
        self.assertNotIn('03:00', answer['best_time'])
        self.assertIn('09:00', answer['best_time'])
        self.assertEqual(answer['species'], '')

    def test_supported_night_remains_possible_for_target_and_method(self):
        rows = self.rows(history(), 'kuha')
        self.assertTrue(rows[0]['eligible'])
        self.assertEqual(rows[0]['supporting_trips'], 2)
        answer = {**ANSWER, 'best_time': '03:00'}
        constrain_answer(answer, rows, {**self.plan, 'species': 'kuha'})
        self.assertEqual(answer['best_time'], '03:00')

    def test_species_and_method_filter_history_and_one_trip_is_not_enough(self):
        self.assertFalse(self.rows(history(), 'ahven')[0]['eligible'])
        self.assertFalse(self.rows(history()[:1], 'kuha')[0]['eligible'])
        other_method = [{**row, 'fishing_method': 'Uistelu'} for row in history()]
        self.assertFalse(self.rows(other_method, 'kuha')[0]['eligible'])
        rows = self.rows(history('Ahven', '09:00'), 'ahven')
        self.assertEqual(rows[1]['supporting_trips'], 2)
        self.assertGreater(rows[1]['priority'], self.rows(history('Kuha', '09:00'), 'ahven')[1]['priority'])

    def test_comparison_keeps_supported_night_at_the_named_place(self):
        supported = [{**r, 'place': 'Oma lahti'} for r in self.rows(history(), 'kuha')]
        unsupported = [{**r, 'place': 'Toinen paikka'} for r in self.rows()]
        answer = {**ANSWER, 'best_time': '03:00', 'recommendation': 'Oma lahti'}
        constrain_answer(answer, supported + unsupported, {**self.plan, 'species': 'kuha'})
        self.assertEqual(answer['best_time'], '03:00')

    def test_solar_season_and_missing_location_are_not_assumed(self):
        self.assertNotEqual(light_at(moment(21, 3, 6), (69, 27)), 'dark')
        self.assertEqual(light_at(moment(21, 3, 12), (69, 27)), 'dark')
        self.assertEqual(light_at(moment(21, 9), None), 'unknown')

    def test_weather_still_affects_priority_and_no_fake_daytime_is_created(self):
        rows = guidance([{'target': moment(21, 9), 'values': {'wind_speed': '12', 'wind_gust': '20'}},
                         {'target': moment(21, 15), 'values': {'wind_speed': '2'}}],
                        (62, 27), [], self.plan, moment(20, 12))
        self.assertGreater(rows[1]['priority'], rows[0]['priority'])
        answer = {**ANSWER, 'best_time': '03:00'}
        constrain_answer(answer, self.rows()[:1], self.plan)
        self.assertIsNone(answer['score'])
        self.assertEqual(answer['best_time'], 'Ei riittävästi perusteltuja ajankohtia')


class TimeIntegrationTests(TestCase):
    @patch('fishinglog.assistant.call_openai', return_value={**ANSWER, 'best_time': '03:00'})
    @patch('fishinglog.assistant.forecast_window', return_value=(samples(), []))
    @patch('fishinglog.assistant.timezone.localtime', return_value=moment(20, 12))
    def test_single_call_receives_guidance_and_unsupported_night_is_corrected(self, now, forecast, api):
        # Patch only the entry clock; helper localtime needs to retain time conversion.
        now.side_effect = lambda value=None: value if value is not None else moment(20, 12)
        user = get_user_model().objects.create_user('time-owner')
        result = ai.advise(user, 'Kannattaako huomenna mennä Kyyvedelle jigaamaan?')
        api.assert_called_once()
        forecast.assert_called_once()
        payload = api.call_args.args[1]
        self.assertEqual(payload['plan']['species'], '')
        self.assertTrue(payload['time_guidance'])
        self.assertTrue(all(r['eligible'] for r in payload['time_guidance']))
        self.assertNotIn('03:00', result['answer']['best_time'])
        self.assertEqual(result['answer']['species'], '')
