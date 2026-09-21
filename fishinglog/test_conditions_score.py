from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from .conditions_score import evaluate
from . import assistant as ai
from .test_assistant import ANSWER
from .test_assistant_time import moment


def sample():
    return {'target': moment(21, 12).isoformat(), 'values': {'wind_speed': 3, 'precipitation': 0,
            'air_temperature': 15, 'cloud_cover': 50, 'air_pressure': 1004}}


def row():
    return {'place': 'Kyyvesi', 'target': moment(21, 12).isoformat(), 'light': 'daylight',
            'period': 'day', 'pressure': {'value': 1004, 'trend': None, 'adjustment': 0}}


class ConditionsTests(SimpleTestCase):
    plan = {'method': 'jiggaus', 'species': ''}

    def test_history_changes_only_confidence(self):
        low = evaluate(sample(), row(), self.plan, 0)
        medium = evaluate(sample(), row(), self.plan, 8)
        self.assertEqual(low['score'], medium['score'])
        self.assertEqual(low['factors'], medium['factors'])
        self.assertEqual(low['confidence'], 'Matala')
        self.assertEqual(medium['confidence'], 'Kohtalainen')
        r = row()
        r['pressure'] = {'value': 1004, 'trend': 'stable', 'adjustment': .1, 'comparison': 'previous', 'delta_hpa': 0, 'hours': 3, 'strength': 'stable'}
        self.assertEqual(evaluate(sample(), r, self.plan, 12)['confidence'], 'Korkea')

    def test_species_absence_neutral_and_explicit_species_refines(self):
        r = row(); r['light'] = 'twilight'
        s = sample(); s['values']['cloud_cover'] = 0
        generic = evaluate(s, r, self.plan)
        specific = evaluate(s, r, {**self.plan, 'species': 'kuha'})
        self.assertEqual(generic['factors'][-1]['value'], 0)
        self.assertAlmostEqual(specific['total'] - generic['total'], .25)
        self.assertEqual((generic['score'], specific['score']), (8, 9))

    def test_sum_rounding_bounds_and_missing_data(self):
        result = evaluate(sample(), row(), self.plan)
        self.assertEqual(result['total'], result['base'] + sum(f['value'] for f in result['factors']))
        self.assertTrue(1 <= result['score'] <= 10)
        self.assertTrue(all(abs(f['value']) <= 1 for f in result['factors']))
        for values in ({}, {'wind_speed': 'NaN'}, {'wind_speed': 3, 'air_temperature': 10}):
            self.assertIsNone(evaluate({'values': values}, row(), self.plan)['score'])
        s = sample(); s['values']['precipitation'] = None
        self.assertEqual(evaluate(s, row(), self.plan)['factors'][2]['value'], 0)


class DeterministicIntegrationTests(TestCase):
    @patch('fishinglog.assistant.call_openai', return_value={**ANSWER, 'score': 1, 'best_time': '03:00'})
    @patch('fishinglog.assistant.forecast_window', return_value=([sample()], []))
    @patch('fishinglog.assistant.timezone.localtime')
    def test_model_cannot_replace_score(self, localtime, forecast, api):
        localtime.side_effect = lambda value=None: value if value is not None else moment(20, 12)
        user = get_user_model().objects.create_user('deterministic')
        result = ai.advise(user, 'Monelta huomenna Kyyvedelle jiggaamaan?')
        api.assert_called_once()
        given = api.call_args.args[1]['conditions_rating']
        self.assertIsNotNone(given)
        self.assertEqual(result['answer']['score'], given['score'])
        self.assertNotEqual(result['answer']['score'], 1)
        self.assertIn('12:00', result['answer']['best_time'])
        self.assertEqual(result['answer']['confidence'], 'Matala')

    @patch('fishinglog.assistant.call_openai', return_value={**ANSWER, 'score': 10})
    @patch('fishinglog.assistant.forecast_window', return_value=([], []))
    def test_missing_forecast_cannot_get_model_score(self, forecast, api):
        user = get_user_model().objects.create_user('no-weather')
        result = ai.advise(user, 'Huomenna Kyyvedelle?')
        self.assertIsNone(result['answer']['score'])
        self.assertEqual(result['answer']['best_time'], 'Ei arvioitavissa')
        api.assert_called_once()
