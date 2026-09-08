import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import requests
from . import assistant as ai
from .models import Trip, Catch, AssistantUsage
from .assistant_limits import reserve, release, record_dispatch
from .test_catch_batch import trip_data

PLAN = {'period': 'today', 'place': 'Kyyvesi', 'method': 'jiggaus', 'species': ''}
ANSWER = {'recommendation': 'Varovaisesti kyllä', 'score': 6, 'best_time': '15:00', 'method': 'Jiggaus',
          'species': 'Kuha', 'rationale': 'Otos on pieni.', 'uncertainty': 'Ei saalistakuuta.'}


class AssistantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('fisher')
        self.other = get_user_model().objects.create_user('private-other')
        self.trip = Trip.objects.create(owner=self.user, **trip_data())
        Trip.objects.create(owner=self.other, **{**trip_data(), 'lake': 'SECRET_OTHER_LAKE'})
        self.client.force_login(self.user)
        self.url = reverse('fishinglog:assistant')

    @patch('fishinglog.assistant_views.advise')
    def test_login_required_and_get_never_calls_ai(self, advise):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.logout()
        for method in ('get', 'post'):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 302)
        advise.assert_not_called()

    @patch('fishinglog.assistant_views.advise')
    def test_invalid_input_csrf_and_concurrent_requests(self, advise):
        for question in ('', 'x' * 1001):
            self.assertEqual(self.client.post(self.url, {'question': question}).status_code, 200)
        reserve(self.user)
        self.assertContains(self.client.post(self.url, {'question': 'Nyt?'}), 'vielä käsittelyssä')
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        self.assertEqual(c.post(self.url, {'question': 'Nyt?'}).status_code, 403)
        advise.assert_not_called()

    def test_history_private_bounded_and_unknown_is_not_empty(self):
        data = ai.history_for(self.user)
        self.assertEqual(data['total_trips'], 1)
        self.assertNotIn('SECRET_OTHER_LAKE', json.dumps(data, default=str))
        self.assertEqual(data['recent_trips'][0]['outcome'], 'saalistieto puuttuu')
        self.trip.no_catch = True
        self.trip.save()
        self.assertEqual(ai.history_for(self.user)['recent_trips'][0]['outcome'], 'ei saalista')
        Trip.objects.bulk_create([Trip(owner=self.user, **trip_data()) for _ in range(45)])
        data = ai.history_for(self.user)
        self.assertLessEqual(data['included_trips'], 40)
        self.assertEqual(data['total_trips'], 46)

    def test_place_priority_and_private_fallback(self):
        self.assertEqual(ai.choose_place(self.user, PLAN, 'Jyväskylä')[0], 'Kyyvesi')
        plan = {**PLAN, 'place': ''}
        self.assertEqual(ai.choose_place(self.user, plan, 'Jyväskylä')[0], 'Jyväskylä')
        self.trip.date = '2024-06-01'
        self.trip.latitude, self.trip.longitude = 62, 26
        self.trip.save()
        self.assertEqual(ai.choose_place(self.user, plan, '')[0], '62.00000,26.00000')
        self.trip.delete()
        self.assertEqual(ai.choose_place(self.user, plan, '')[0], '')

    @patch('fishinglog.assistant.forecast_window', return_value=([{'target': '2026-09-07T15:00:00+03:00', 'values': {'wind_speed':'3'}}], []))
    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    def test_own_context_only_and_forecast_used(self, api, forecast):
        result = ai.advise(self.user, 'Tänään Kyyvedelle?', 'Helsinki')
        self.assertEqual(forecast.call_args.args[0], 'Kyyvesi')
        context = api.call_args_list[0].args[1]
        self.assertNotIn('SECRET_OTHER_LAKE', json.dumps(context, default=str))
        self.assertNotIn('private-other', json.dumps(context, default=str))
        self.assertEqual(context['weather'][0]['values']['wind_speed'], '3')
        self.assertEqual(result['answer']['score'], 6)
        api.assert_called_once()

    @patch('fishinglog.assistant.forecast_window', side_effect=ai.weather.WeatherError('network'))
    @patch('fishinglog.assistant.call_openai', return_value=dict(ANSWER))
    def test_weather_failure_prevents_unsupported_score(self, api, forecast):
        result = ai.advise(self.user, 'Tänään?')
        self.assertTrue(result['warning'])
        self.assertIsNone(result['answer']['score'])
        self.assertEqual(result['answer']['best_time'], 'Ei arvioitavissa')

    @patch('fishinglog.assistant.forecast_window')
    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    def test_history_never_fetches_forecast(self, api, forecast):
        ai.advise(self.user, 'Millä vieheellä olen saanut?')
        forecast.assert_not_called()

    @patch('fishinglog.assistant_views.advise', side_effect=ai.AssistantError('Palvelu ei vastaa'))
    def test_api_error_does_not_break_other_pages(self, advise):
        self.assertContains(self.client.post(self.url, {'question': 'Nyt?'}), 'Palvelu ei vastaa')
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIsNone(cache.get(f'assistant-request:{self.user.pk}'))

    @patch('fishinglog.assistant_views.advise')
    def test_ai_output_is_escaped_and_user_id_cannot_be_forged(self, advise):
        advise.return_value = {'answer': {**ANSWER, 'rationale':'<script>alert(1)</script>'}, 'history_count':1, 'history_total':1}
        response = self.client.post(self.url, {'question': 'Nyt?', 'user_id': self.other.pk})
        self.assertEqual(advise.call_args.args[0].pk, self.user.pk)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert')
        self.assertIn('no-store', response.headers['Cache-Control'])


class OpenAITransportTests(TestCase):
    @patch.dict(os.environ, {'OPENAI_API_KEY': ''})
    @patch('fishinglog.assistant.requests.post')
    def test_missing_key_does_not_call_network(self, post):
        with self.assertRaises(ai.AssistantError):
            ai.call_openai('instructions', {}, ai.PLAN, 350)
        post.assert_not_called()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-not-a-real-key'})
    @patch('fishinglog.assistant.requests.post')
    def test_transport_and_invalid_responses(self, post):
        response = post.return_value.__enter__.return_value
        good = {'status': 'completed', 'output': [{'type':'message','content':[{'type':'output_text','text':json.dumps(PLAN)}]}]}
        response.iter_content.return_value = [json.dumps(good).encode()]
        self.assertEqual(ai.call_openai('instructions', {}, ai.PLAN, 350), PLAN)
        kwargs = post.call_args.kwargs
        self.assertFalse(kwargs['json']['store'])
        self.assertEqual(kwargs['json']['max_output_tokens'], 350)
        self.assertFalse(kwargs['allow_redirects'])
        for content in [b'not json', b'{}', json.dumps({**good, 'status':'incomplete'}).encode(), b'x'*150001]:
            response.iter_content.return_value = [content]
            with self.assertRaises(ai.AssistantError):
                ai.call_openai('instructions', {}, ai.PLAN, 350)
        post.side_effect = requests.Timeout('secret provider diagnostic')
        with self.assertRaises(ai.AssistantError) as error:
            ai.call_openai('instructions', {}, ai.PLAN, 350)
        self.assertNotIn('secret provider diagnostic', str(error.exception))


class ForecastWindowTests(TestCase):
    @patch('fishinglog.assistant.weather.parse_response', return_value={'values': {}})
    @patch('fishinglog.assistant.weather.download', return_value=b'<xml/>')
    @patch('fishinglog.assistant.weather.resolve_place', return_value={'latitude':62, 'longitude':26})
    def test_three_days_are_compared_in_one_request(self, resolve, download, parse):
        now = timezone.make_aware(datetime(2026, 9, 7, 10, 0))
        samples, missing = ai.forecast_window('Kyyvesi', 'next3', now)
        self.assertGreater(len(samples), 10)
        self.assertEqual(len({row['target'][:10] for row in samples}), 3)
        self.assertTrue(all(datetime.fromisoformat(row['target']) >= now for row in samples))
        download.assert_called_once()
        samples, _ = ai.forecast_window('Kyyvesi', 'tomorrow', now)
        self.assertTrue(all(row['target'].startswith('2026-09-08') for row in samples))

    @patch('fishinglog.assistant.weather.fetch_weather', return_value={'values': {}})
    def test_now_uses_current_weather(self, fetch):
        now = timezone.localtime()
        ai.forecast_window('Kyyvesi', 'now', now)
        fetch.assert_called_once_with('Kyyvesi', now)


class UsageLimitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('limited')
        self.client.force_login(self.user)
        self.url = reverse('fishinglog:assistant')

    @patch('fishinglog.assistant_views.advise')
    def test_eleventh_request_never_calls_assistant_even_after_cache_clear(self, advise):
        def dispatched(*args, **kwargs):
            kwargs['before_send']()
            raise ai.AssistantError('Unavailable')
        advise.side_effect = dispatched
        for _ in range(10):
            self.client.post(self.url, {'question':'Nyt?'})
        cache.clear()
        response = self.client.post(self.url, {'question':'Nyt?'})
        self.assertContains(response, 'Tuntiraja täyttyi')
        self.assertEqual(advise.call_count, 11)
        usage = AssistantUsage.objects.get(user=self.user)
        self.assertEqual(len(usage.attempts), 10)
        self.assertIsNone(usage.busy_until)
        self.assertEqual(set(usage.__dict__) - {'_state'}, {'id','user_id','attempts','version','busy_until'})

    def test_rolling_hour_and_users_are_independent(self):
        from datetime import timedelta
        now = timezone.now()
        with patch('fishinglog.assistant_limits.timezone.now', return_value=now):
            for _ in range(10):
                reservation = reserve(self.user)
                record_dispatch(reservation)
                release(reservation)
            other = get_user_model().objects.create_user('separate')
            release(reserve(other))
        with patch('fishinglog.assistant_limits.timezone.now', return_value=now + timedelta(minutes=59)):
            reservation = reserve(self.user)
            with self.assertRaises(ai.AssistantError): record_dispatch(reservation)
            release(reservation)
        with patch('fishinglog.assistant_limits.timezone.now', return_value=now + timedelta(hours=1)):
            reservation = reserve(self.user)
            record_dispatch(reservation)
            release(reservation)
        self.assertEqual(len(AssistantUsage.objects.get(user=self.user).attempts), 1)

    def test_overlapping_requests_and_failed_compare_swap_are_rejected(self):
        reservation = reserve(self.user)
        with self.assertRaises(ai.AssistantError): reserve(self.user)
        release(reservation)
        with patch('django.db.models.query.QuerySet.update', return_value=0):
            with self.assertRaises(ai.AssistantError): reserve(self.user)

    @patch.dict(os.environ, {'OPENAI_API_KEY':'test-only-key'})
    @patch('fishinglog.assistant.requests.post', side_effect=requests.Timeout('test-only-key'))
    def test_timeout_is_30_seconds_without_retry_or_secret_output(self, post):
        with self.assertRaises(ai.AssistantError) as error:
            ai.call_openai('instructions', {}, ai.ANSWER, 1100)
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs['timeout'], 30)
        self.assertEqual(post.call_args.kwargs['json']['max_output_tokens'], 1100)
        self.assertNotIn('test-only-key', str(error.exception))

    def test_local_routing_needs_no_api(self):
        for question, period, place in [
            ('Kannattaako tänään lähteä Kyyvedelle jiggaamaan?', 'today', 'Kyyvesi'),
            ('Kannattaako huomenna uistella kuhaa?', 'tomorrow', ''),
            ('Milloin seuraavan 3 päivän aikana olisi paras hetki kalastaa?', 'next3', ''),
            ('Millaisella säällä olen saanut eniten haukia?', 'history', '')]:
            plan = ai.interpret_question(question)
            self.assertEqual(plan['period'], period)
            self.assertEqual(plan['place'], place)


class KeyDiagnosticsTests(TestCase):
    def test_diagnostics_read_current_environment_without_calls_or_key_disclosure(self):
        from io import StringIO
        from django.core.management import call_command
        user = get_user_model().objects.create_user('diagnostics')
        self.client.force_login(user)
        with patch('fishinglog.assistant.requests.post') as post:
            for value, status in [('', 'ei'), ('test-only-placeholder', 'kyllä'), ('', 'ei')]:
                with patch.dict(os.environ, {'OPENAI_API_KEY': value}):
                    response = self.client.get(reverse('fishinglog:assistant'))
                    self.assertNotContains(response, 'OPENAI_API_KEY löytyi:')
                    if value:
                        self.assertNotContains(response, 'OPENAI_API_KEY puuttuu')
                        self.assertNotContains(response, value)
                    else:
                        self.assertContains(response, 'OPENAI_API_KEY puuttuu')
                    output = StringIO()
                    call_command('check_openai_key', stdout=output)
                    self.assertEqual(output.getvalue().strip(), 'OPENAI_API_KEY löytyi: ' + status)
            post.assert_not_called()


class DispatchQuotaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('dispatch-test')
        self.client.force_login(self.user)
        self.url = reverse('fishinglog:assistant')

    @patch.dict(os.environ, {'OPENAI_API_KEY': ''})
    @patch('fishinglog.assistant.requests.post')
    def test_missing_key_invalid_form_and_clarification_do_not_charge(self, post):
        for question in ['', 'x'*1001, 'Mitä?', 'Millä vieheellä olen saanut kalaa?']:
            self.client.post(self.url, {'question': question})
        self.assertEqual(AssistantUsage.objects.get(user=self.user).attempts, [])
        post.assert_not_called()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-not-real'})
    @patch('fishinglog.assistant.requests.post', side_effect=requests.Timeout('test'))
    def test_only_ten_http_dispatches_including_timeouts(self, post):
        for _ in range(10):
            self.client.post(self.url, {'question': 'Millä vieheellä olen saanut kalaa?'})
        self.assertEqual(post.call_count, 10)
        self.assertEqual(len(AssistantUsage.objects.get(user=self.user).attempts), 10)
        response = self.client.post(self.url, {'question': 'Millä vieheellä olen saanut kalaa?'})
        self.assertContains(response, 'Tuntiraja täyttyi')
        self.assertEqual(post.call_count, 10)
