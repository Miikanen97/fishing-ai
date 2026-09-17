from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .assistant import AssistantError
from .models import Trip, Catch, FishingSpot
from .test_catch_batch import trip_data


class PackageTwoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ux-owner')
        self.other = get_user_model().objects.create_user('ux-other')
        self.client.force_login(self.user)
        self.spot = FishingSpot.objects.create(user=self.user, name='Oma ranta')
        self.foreign = FishingSpot.objects.create(user=self.other, name='Salainen ranta')

    def test_spot_counts_species_privacy_and_constant_query_count(self):
        trip = Trip.objects.create(owner=self.user, fishing_spot=self.spot, **trip_data())
        Trip.objects.create(owner=self.user, fishing_spot=self.spot, **trip_data())
        Catch.objects.create(time='12:00', trip=trip, species='Ahven')
        Catch.objects.create(time='12:00', trip=trip, species='Ahven')
        # Even inconsistent cross-owner links must not expose another user's history.
        foreign = Trip.objects.create(owner=self.other, fishing_spot=self.spot, **trip_data())
        Catch.objects.create(time='12:00', trip=foreign, species='Salainen laji')
        url = reverse('fishinglog:spots')
        with CaptureQueriesContext(connection) as initial:
            response = self.client.get(url)
        row = response.context['spots'][0]
        self.assertEqual((row['trip_count'], row['catch_count']), (2, 2))
        self.assertEqual(row['species_summary'], 'Ahven')
        self.assertContains(response, 'Karttasijainti puuttuu')
        self.assertNotContains(response, 'Salainen')
        FishingSpot.objects.bulk_create([FishingSpot(user=self.user, name=f'Paikka {i}') for i in range(20)])
        with CaptureQueriesContext(connection) as expanded:
            self.client.get(url)
        self.assertEqual(len(initial), len(expanded))
        self.assertLessEqual(len(expanded), 4)

    @patch('fishinglog.views.home_weather', return_value={})
    def test_home_own_data_and_shared_trip_states(self, weather):
        Trip.objects.create(owner=self.user, **trip_data())
        Trip.objects.create(owner=self.user, no_catch=True, **trip_data())
        caught = Trip.objects.create(owner=self.user, **trip_data())
        Catch.objects.create(time='12:00', trip=caught, species='Kuha')
        Trip.objects.create(owner=self.other, **{**trip_data(), 'location': 'Salainen reissu'})
        response = self.client.get(reverse('fishinglog:home'))
        self.assertEqual(response.context['trip_count'], 3)
        self.assertEqual(response.context['catch_count'], 1)
        self.assertTemplateUsed(response, 'fishinglog/trip_cards.html')
        for text in ('Ei saalistietoa', 'Ei saalista', 'Saaliit (1)', 'Kuha'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Salainen reissu')
        weather.assert_called_once_with(self.user)

    @patch('fishinglog.assistant_views.advise', return_value=None)
    def test_saved_places_and_free_text_use_existing_submission(self, advise):
        url = reverse('fishinglog:assistant')
        response = self.client.get(url)
        self.assertContains(response, 'Oma ranta')
        self.assertNotContains(response, 'Salainen ranta')
        self.assertContains(response, 'Muu paikka')
        self.assertContains(response, 'Kysy avustajalta')
        advise.assert_not_called()
        for place in ('Oma ranta', 'Jämsä'):
            self.client.post(url, {'question': 'Mihin huomenna?', 'place': place})
            self.assertEqual(advise.call_args.args[2], place)
        self.assertEqual(advise.call_count, 2)

    @patch('fishinglog.assistant_views.api_key_configured', return_value=False)
    @patch('fishinglog.assistant_views.advise', side_effect=AssistantError('OPENAI_API_KEY puuttuu'))
    def test_production_and_development_missing_key_messages(self, advise, configured):
        url = reverse('fishinglog:assistant')
        for debug in (False, True):
            with override_settings(DEBUG=debug):
                for response in (self.client.get(url), self.client.post(url, {'question': 'Huomenna?'})):
                    if debug:
                        self.assertContains(response, 'OPENAI_API_KEY')
                    else:
                        self.assertContains(response, 'ei ole juuri nyt käytettävissä')
                        self.assertNotContains(response, 'OPENAI_API_KEY')
                        self.assertNotContains(response, 'PowerShell')

    @patch('fishinglog.assistant_views.advise')
    def test_quick_questions_have_valid_existing_routes(self, advise):
        import re
        from .assistant import interpret_question
        response = self.client.get(reverse('fishinglog:assistant'))
        questions = re.findall(r'data-question="([^"]+)"', response.content.decode())
        self.assertEqual(len(questions), 4)
        for question in questions:
            plan = interpret_question(question)
            self.assertIn(plan['period'], ('tomorrow', 'history'))
            self.assertEqual(plan['place'], '')
        advise.assert_not_called()
