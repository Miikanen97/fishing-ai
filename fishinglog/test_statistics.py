from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Trip, Catch, FishingSpot
from .test_catch_batch import trip_data

class StatisticsTests(TestCase):
    def test_ownership_counts_records_and_boundaries(self):
        user = get_user_model().objects.create_user('stats')
        other = get_user_model().objects.create_user('other')
        spot = FishingSpot.objects.create(user=user, name='Oma')
        FishingSpot.objects.create(user=other, name='SECRET')
        trip = Trip.objects.create(owner=user, fishing_spot=spot, **trip_data())
        Trip.objects.create(owner=user, **{**trip_data(), 'no_catch':True})
        Trip.objects.create(owner=user, **trip_data())
        foreign = Trip.objects.create(owner=other, fishing_spot=spot, **trip_data())
        Catch.objects.create(trip=foreign, species='SECRET', time='12:00', weight=99)
        for time in ['05:00','10:00','16:00','22:00']:
            Catch.objects.create(trip=trip, species='Kuha', time=time, weight=1, length='0.5', lure_name='Jigi', lure_color='Vihreä')
        url = reverse('fishinglog:statistics')
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(user)
        response = self.client.get(url, {'user':other.pk})
        self.assertNotContains(response,'SECRET')
        for key, value in [('total',3),('fish_total',4),('productive',1),('empty',1),('unknown',1)]:
            self.assertEqual(response.context[key],value)
        self.assertEqual([r['count'] for r in response.context['periods']], [1,1,1,1])
        self.assertEqual(response.context['spots'][0]['count'],4)
        self.assertEqual(response.context['overall']['heaviest'].weight,1)

    def test_empty(self):
        user = get_user_model().objects.create_user('empty')
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('fishinglog:statistics')), 'Havaintoja on vielä vähän')

    def test_unused_places_and_trip_state_totals(self):
        user = get_user_model().objects.create_user('states')
        self.client.force_login(user)
        FishingSpot.objects.create(user=user, name='Käyttämätön paikka')
        spot = FishingSpot.objects.create(user=user, name='Saaliiton paikka')
        Trip.objects.create(owner=user, fishing_spot=spot, **{**trip_data(), 'no_catch':True})
        Trip.objects.create(owner=user, **trip_data())
        trip = Trip.objects.create(owner=user, **{**trip_data(), 'no_catch':True})
        Catch.objects.create(trip=trip, species='Hauki', time='12:00')
        response = self.client.get(reverse('fishinglog:statistics'))
        self.assertContains(response, 'Ei saalistietoa')
        self.assertNotContains(response, 'Käyttämätön paikka')
        self.assertContains(response, 'Saaliiton paikka')
        self.assertContains(response, 'Pieni otos')
        data = response.context
        self.assertEqual(data['total'],data['productive']+data['empty']+data['unknown'])
        self.assertEqual((data['productive'],data['empty'],data['unknown']),(1,1,1))

    def test_same_and_different_record_fish(self):
        user = get_user_model().objects.create_user('records')
        self.client.force_login(user)
        trip = Trip.objects.create(owner=user, **trip_data())
        Catch.objects.create(trip=trip, species='Kuha', time='12:00', weight=3, length='0.6')
        url = reverse('fishinglog:statistics')
        self.assertContains(self.client.get(url), 'Sama kala pitää hallussaan molempia ennätyksiä.')
        Catch.objects.create(trip=trip, species='Hauki', time='13:00', weight=2, length='0.8')
        response = self.client.get(url)
        self.assertContains(response, 'Paino- ja pituusennätys kuuluvat eri kaloille.')
        self.assertEqual(response.context['overall']['heaviest'].species,'Kuha')
        self.assertEqual(response.context['overall']['longest'].species,'Hauki')
