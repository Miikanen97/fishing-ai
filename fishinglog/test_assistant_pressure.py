from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from .assistant_pressure import pressure_trends, describe_pressure
from .assistant_time import guidance, pressure_summary, constrain_answer
from .test_assistant_time import moment
from .test_assistant import ANSWER
from . import assistant as ai


def forecast(values, step=3, first=9):
    return [{'target': (moment(21, first) + timedelta(hours=i*step)).isoformat(),
             'values': {'air_pressure': value, 'wind_speed': '2', 'precipitation': '0'}}
            for i, value in enumerate(values)]


class PressureTests(SimpleTestCase):
    plan = {'period': 'tomorrow', 'method': 'jiggaus', 'species': ''}

    def test_rising_falling_and_stable(self):
        for values, expected, label in [([1002, 1004], 'rising', 'nousussa'),
                                        ([1006, 1004], 'falling', 'laskussa'),
                                        ([1004.1, 1004], 'stable', 'pysynyt melko vakaana')]:
            row = list(pressure_trends(forecast(values)).values())[-1]
            self.assertEqual(row['trend'], expected)
            self.assertEqual(row['value'], 1004)
            self.assertEqual(row['hours'], 3)
            self.assertIn('Ilmanpaine 1004 hPa, ' + label, describe_pressure(row))
            self.assertEqual(row['comparison'], 'previous')

    def test_strength_is_time_normalized_and_input_is_sorted(self):
        quick = list(pressure_trends(forecast([1000, 1001], step=1)).values())[-1]
        slow = list(pressure_trends(list(reversed(forecast([1000, 1001], step=6)))).values())[-1]
        self.assertEqual(quick['strength'], 'strong')
        self.assertEqual(slow['strength'], 'stable')
        self.assertEqual(quick['rate_hpa_per_hour'], 1)
        self.assertAlmostEqual(slow['rate_hpa_per_hour'], .167)

    def test_missing_single_invalid_gap_and_duplicate_are_not_trends(self):
        cases = [forecast([1004]), forecast([None, 1004]), forecast([1004, None, 1005]),
                 forecast([1004, 'NaN']), forecast([1004, 'Infinity']), forecast([1004, 0]),
                 forecast([1004, 1005], step=12), forecast([1004])*2]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertTrue(all(r['trend'] is None and r['adjustment'] == 0 for r in pressure_trends(rows).values()))
        self.assertIn('ei ole riittävästi', describe_pressure({'value': 1004, 'trend': None}))
        self.assertIn('ei ole ennustetietoa', describe_pressure({'value': None}))

    def test_first_point_uses_forward_comparison_without_claiming_past_change(self):
        row = list(pressure_trends(forecast([1004, 1004])).values())[0]
        self.assertEqual(row['comparison'], 'next')
        self.assertIn('seuraavan 3 h', describe_pressure(row))
        self.assertNotIn('pysynyt', describe_pressure(row))

    def test_contribution_is_small_and_night_rule_still_applies(self):
        rows = guidance(forecast([1004, 1004, 1000], first=3), (62, 27), [], self.plan, moment(20, 12))
        baseline = guidance(forecast([None, None, None], first=3), (62, 27), [], self.plan, moment(20, 12))
        self.assertFalse(rows[0]['eligible'])
        for row, original in zip(rows, baseline):
            self.assertLessEqual(abs(row['priority'] - original['priority']), .201)
            self.assertEqual(row['eligible'], original['eligible'])
        self.assertNotEqual(rows[0]['priority'], baseline[0]['priority'])
        answer = {**ANSWER, 'best_time': '03:00'}
        constrain_answer(answer, rows, self.plan)
        self.assertNotIn('03:00', answer['best_time'])

    def test_selected_date_and_place_do_not_mix_pressure_series(self):
        a = guidance(forecast([1002, 1004]), (62, 27), [], self.plan, moment(20, 12), 'Paikka A')
        b = guidance(forecast([1006, 1004]), (63, 26), [], self.plan, moment(20, 12), 'Paikka B')
        answer = {**ANSWER, 'best_time': '21.09.2026 klo 12:00', 'recommendation': 'Paikka B'}
        self.assertIn('laskussa', pressure_summary(answer, a+b))
        answer['recommendation'] = ''
        self.assertIn('ei voitu yhdistää', pressure_summary(answer, a+b))
        answer['best_time'] = '22.09.2026 klo 12:00'
        self.assertIn('ei voitu yhdistää', pressure_summary(answer, a))


class PressureIntegrationTests(TestCase):
    @patch('fishinglog.assistant.call_openai', return_value={**ANSWER, 'best_time': '21.09.2026 klo 12:00'})
    @patch('fishinglog.assistant.forecast_window', return_value=(forecast([1006, 1004]), []))
    @patch('fishinglog.assistant.timezone.localtime')
    def test_single_call_and_pressure_visible_in_answer(self, localtime, weather, api):
        localtime.side_effect = lambda value=None: value if value is not None else moment(20, 12)
        user = get_user_model().objects.create_user('pressure-owner')
        self.client.force_login(user)
        response = self.client.post(reverse('fishinglog:assistant'), {'question': 'Kannattaako huomenna Kyyvedelle jigaamaan?'})
        self.assertContains(response, 'Ilmanpaine 1004 hPa, laskussa')
        api.assert_called_once()
        weather.assert_called_once()
        options = api.call_args.args[1]['time_guidance']
        self.assertTrue(all(row['pressure']['trend'] == 'falling' for row in options))
