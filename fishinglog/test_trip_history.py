from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Trip, Catch
from .test_catch_batch import trip_data

class TripHistoryTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('history-user')
        self.other=get_user_model().objects.create_user('other-history')
        self.client.force_login(self.user)
        self.caught=Trip.objects.create(owner=self.user,**{**trip_data(),'location':'Selkä','date':'2026-06-01'})
        self.empty=Trip.objects.create(owner=self.user,**{**trip_data(),'location':'Lahti','date':'2026-06-02','no_catch':True})
        self.unknown=Trip.objects.create(owner=self.user,**{**trip_data(),'location':'Ranta','date':'2026-06-03'})
        self.foreign=Trip.objects.create(owner=self.other,**{**trip_data(),'location':'SECRET'})
        Catch.objects.create(trip=self.caught,species='Hauki',time='10:00',weight='6.2',length='1.02')
        Catch.objects.create(trip=self.caught,species='Ahven',time='11:00')
        Catch.objects.create(trip=self.foreign,species='Salainen kala',time='10:00')
        self.url=reverse('fishinglog:trip_list')

    def test_filters_are_owned_and_catch_count_not_reduced_by_species(self):
        for params,expected in [({'q':'selkä'},self.caught),({'species':'hauki'},self.caught),({'outcome':'caught'},self.caught),({'outcome':'empty'},self.empty),({'outcome':'unknown'},self.unknown),({'start':'2026-06-02','end':'2026-06-02'},self.empty)]:
            with self.subTest(params=params):
                response=self.client.get(self.url,params)
                self.assertEqual([t.pk for t in response.context['trips']],[expected.pk])
                self.assertNotContains(response,'SECRET')
                if expected==self.caught:
                    self.assertEqual(response.context['trips'][0].catch_count,2)
        response=self.client.get(self.url,{'start':'bad'})
        self.assertTrue(response.context['filters'].errors)
        self.assertEqual(self.client.get(self.foreign.get_absolute_url()).status_code,404)

    def test_pagination_and_bounded_query_count(self):
        Trip.objects.bulk_create([Trip(owner=self.user,**{**trip_data(),'location':'Suodatettu'}) for _ in range(25)])
        # session, user, paginator count, page trips and one grouped species query.
        with self.assertNumQueries(5):
            response=self.client.get(self.url,{'q':'Suodatettu'})
        self.assertEqual(len(response.context['trips']),12)
        self.assertContains(response,'?q=Suodatettu&amp;page=2')
        self.assertEqual(len(self.client.get(self.url,{'q':'Suodatettu','page':3}).context['trips']),1)

    def test_compact_cards_states_and_missing_values(self):
        response=self.client.get(self.url)
        self.assertContains(response,'Hauki ×1')
        self.assertContains(response,'Ahven ×1')
        self.assertContains(response,'Ei saalistietoa')
        self.assertContains(response,'Ei saalista')
        response=self.client.get(self.caught.get_absolute_url())
        self.assertContains(response,'6,2 kg')
        self.assertContains(response,'1,02 m')
        self.assertNotContains(response,'Ei muistiinpanoja')
        self.assertContains(self.client.get(self.unknown.get_absolute_url()),'Saalistietoa ei ole vielä lisätty')
        self.assertNotContains(self.client.get(self.empty.get_absolute_url()),'Saalistietoa ei ole vielä lisätty')
        self.unknown.water_temperature=None
        self.unknown.depth=None
        self.unknown.boat_speed=0
        self.unknown.notes=''
        self.unknown.save()
        response=self.client.get(self.unknown.get_absolute_url())
        self.assertNotContains(response,'Veden lämpötila')
        self.assertContains(response,'Veneen nopeus')

    def test_detail_renders_all_outcomes_without_custom_tag_registration(self):
        from django.template import engines
        from unittest.mock import patch
        engine = engines['django'].engine
        libraries = {name:library for name,library in engine.template_libraries.items() if name != 'trip_display'}
        with patch.dict(engine.template_libraries, libraries, clear=True):
            for loader in engine.template_loaders:
                if hasattr(loader, 'reset'):
                    loader.reset()
            for trip, expected in [(self.caught,'Saaliit (2)'), (self.empty,'Ei saalista'), (self.unknown,'Saalistietoa ei ole vielä lisätty')]:
                with self.subTest(trip=trip.pk):
                    response = self.client.get(trip.get_absolute_url())
                    self.assertEqual(response.status_code,200)
                    self.assertTemplateUsed(response,'fishinglog/trip_detail.html')
                    self.assertContains(response,expected)
                    if trip == self.caught:
                        self.assertContains(response,'6,2 kg')
                        self.assertContains(response,'1,02 m')
