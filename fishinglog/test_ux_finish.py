from collections import Counter
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Trip, Catch
from .test_catch_batch import trip_data


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.descriptions = []
        self.labels = []
        self.controls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        self.descriptions.extend(attrs.get('aria-describedby', '').split())
        if tag == 'label':
            self.labels.append(attrs.get('for'))
        if tag in ('input', 'select', 'textarea') and attrs.get('type') not in ('hidden', 'submit'):
            if not attrs.get('aria-label'):
                self.controls.append(attrs.get('id'))


class UXFinishTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('finish')
        self.client.force_login(self.user)

    def assert_accessible_fields(self, response):
        self.assertEqual(response.status_code, 200)
        markup = Markup(response.content.decode())
        self.assertFalse([key for key, n in Counter(markup.ids).items() if n > 1])
        self.assertFalse(set(markup.descriptions) - set(markup.ids))
        self.assertFalse(set(markup.controls) - set(markup.labels))

    @patch('requests.sessions.Session.request', side_effect=AssertionError('No external calls'))
    def test_labels_and_descriptions_on_forms_and_errors(self, network):
        trip = Trip.objects.create(owner=self.user, **trip_data())
        catch = Catch.objects.create(trip=trip, time='12:00', species='Kuha')
        routes = [('fishinglog:trip_create', []), ('fishinglog:trip_update', [trip.pk]),
                  ('fishinglog:catch_create', [trip.pk]), ('fishinglog:catch_update', [trip.pk, catch.pk]),
                  ('fishinglog:assistant', []), ('fishinglog:settings', []), ('fishinglog:spots', []),
                  ('account', []), ('password_change', []), ('delete_account', [])]
        for name, args in routes:
            with self.subTest(name=name):
                self.assert_accessible_fields(self.client.get(reverse(name, args=args)))
        response = self.client.post(reverse('fishinglog:trip_create'), {'location': 'Säilyvä nimi', 'date': 'invalid'})
        self.assert_accessible_fields(response)
        self.assertContains(response, 'Säilyvä nimi')
        self.client.logout()
        for name in ('login', 'register'):
            self.assert_accessible_fields(self.client.get(reverse(name)))
            self.assert_accessible_fields(self.client.post(reverse(name), {'username': ''}))
        network.assert_not_called()

    @patch('fishinglog.views.home_weather', return_value={})
    @patch('fishinglog.assistant_views.advise')
    def test_empty_user_views_and_navigation(self, advise, weather):
        for route in ('home', 'statistics', 'trip_list', 'spots', 'assistant'):
            response = self.client.get(reverse('fishinglog:' + route))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'aria-controls="navigation-links"')
            self.assertContains(response, 'aria-expanded="false"')
            self.assertContains(response, '>Etusivu</a>')
        advise.assert_not_called()
