from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .assistant_scoring import breakdown
from .assistant_time import guidance
from .test_assistant_pressure import forecast
from .test_assistant_time import moment
from .test_assistant import ANSWER


class BreakdownTests(SimpleTestCase):
    plan = {'method': 'jiggaus', 'species': '', 'period': 'tomorrow'}

    def rows(self, history=()):
        return guidance(forecast([1002, 1004]), (62, 27), history, self.plan, moment(20, 12), 'Kyyvesi')

    def test_exact_existing_sum_and_pressure_effect(self):
        row = self.rows()[-1]
        self.assertEqual(round(sum(value for _, value, _ in row['score_factors']), 2), row['priority'])
        self.assertEqual(row['priority'], round(1 - 2/3 - .1, 2))
        audit = breakdown({'best_time': '21.09.2026 klo 12:00'}, [row])
        pressure = next(f for f in audit['factors'] if f['label'] == 'Ilmanpaine ja painetrendi')
        self.assertEqual(pressure['impact'], '-0,10')
        self.assertIn('nousussa', pressure['detail'])

    def test_missing_history_does_not_reduce_weather_points(self):
        history = [{'date': '2026-09-01', 'start_time': '10:00', 'fishing_method': 'jiggaus',
                    'catches': [{'species': 'kuha', 'time': '12:00'}]}]
        empty, supported = self.rows()[-1], self.rows(history)[-1]
        self.assertEqual(empty['score_factors'][:-1], supported['score_factors'][:-1])
        self.assertEqual(empty['score_factors'][-1][1], 0)
        self.assertEqual(supported['score_factors'][-1][1], 2)

    def test_missing_or_ambiguous_answer_not_guessed(self):
        self.assertFalse(breakdown({}, self.rows())['available'])
        self.assertFalse(breakdown({'best_time': '12:00'}, self.rows()*2)['available'])
        self.assertFalse(breakdown({'best_time': '12:00'}, [])['available'])


class BreakdownIntegrationTests(TestCase):
    @patch('fishinglog.assistant.call_openai', return_value={**ANSWER, 'score': 3, 'best_time': '21.09.2026 klo 12:00'})
    @patch('fishinglog.assistant.forecast_window', return_value=(forecast([1002, 1004]), []))
    @patch('fishinglog.assistant.timezone.localtime')
    def test_render_and_model_score_unchanged(self, localtime, weather, api):
        localtime.side_effect = lambda value=None: value if value is not None else moment(20, 12)
        user = get_user_model().objects.create_user('score-owner')
        self.client.force_login(user)
        response = self.client.post(reverse('fishinglog:assistant'), {'question': 'Kannattaako huomenna Kyyvedelle jigaamaan?'})
        self.assertContains(response, 'Pisteiden muodostuminen')
        self.assertContains(response, 'Puuttuvasta historiasta ei vähennetä')
        self.assertContains(response, 'nousussa')
        self.assertEqual(response.context['result']['answer']['score'], 3)
        api.assert_called_once()
        for row in api.call_args.args[1]['time_guidance']:
            self.assertNotIn('score_factors', row)
            self.assertNotIn('requested_species', row)
