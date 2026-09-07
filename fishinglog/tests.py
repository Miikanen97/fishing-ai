from django.test import Client, TestCase
from django.urls import reverse
from .models import Catch, Trip


class FishingLogTests(TestCase):
    def setUp(self):
        self.data = dict(date='2026-09-07', lake='Saimaa', location='Selkä', start_time='08:00', end_time='16:00', weather='Pilvinen', air_temperature='-2.5', water_temperature='12.0', fishing_method='Jiggaus', depth='8.5', boat_speed='0', notes='Testireissu')
        self.trip = Trip.objects.create(**self.data)
        self.catch_data = dict(species='Kuha', length='0.525', weight='1.5', lure_name='Jigi', lure_color='Vihreä', time='10:30', depth='8.0', notes='Ensimmäinen')
        self.catch = Catch.objects.create(trip=self.trip, **self.catch_data)

    def batch(self, data):
        return {'catches-TOTAL_FORMS': '1', 'catches-INITIAL_FORMS': '0',
                **{f'catches-0-{key}': value for key, value in data.items()}}

    def url(self, name, *args):
        return reverse('fishinglog:' + name, args=args)

    def test_all_pages(self):
        routes = [('home', ()), ('trip_list', ()), ('trip_create', ()), ('trip_detail', (self.trip.pk,)), ('trip_update', (self.trip.pk,)), ('trip_delete', (self.trip.pk,)), ('catch_create', (self.trip.pk,)), ('catch_update', (self.trip.pk, self.catch.pk)), ('catch_delete', (self.trip.pk, self.catch.pk))]
        for name, args in routes:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name, *args)).status_code, 200)
        response = self.client.get(self.trip.get_absolute_url())
        for value in ['Saimaa', 'Kuha', 'Vihreä', 'Pilvinen', 'Ensimmäinen']:
            self.assertContains(response, value)

    def test_trip_create_update(self):
        response = self.client.post(self.url('trip_create'), self.data)
        trip = Trip.objects.latest('pk')
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(Trip.objects.count(), 2)
        response = self.client.post(self.url('trip_update', trip.pk), {**self.data, 'lake': 'Päijänne'})
        self.assertRedirects(response, trip.get_absolute_url())
        trip.refresh_from_db()
        self.assertEqual(trip.lake, 'Päijänne')
        self.assertContains(self.client.get(self.url('trip_update', trip.pk)), '2026-09-07')

    def test_multiple_catches_update_and_delete(self):
        response = self.client.post(self.url('catch_create', self.trip.pk), self.batch(self.catch_data))
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.assertEqual(self.trip.catches.count(), 2)
        url = self.url('catch_update', self.trip.pk, self.catch.pk)
        self.assertRedirects(self.client.post(url, {**self.catch_data, 'species': 'Ahven'}), self.trip.get_absolute_url())
        self.catch.refresh_from_db()
        self.assertEqual(self.catch.species, 'Ahven')
        url = self.url('catch_delete', self.trip.pk, self.catch.pk)
        self.client.get(url)
        self.assertTrue(Catch.objects.filter(pk=self.catch.pk).exists())
        self.assertRedirects(self.client.post(url), self.trip.get_absolute_url())
        self.assertEqual(self.trip.catches.count(), 1)

    def test_trip_delete_cascades_only_after_post(self):
        url = self.url('trip_delete', self.trip.pk)
        self.client.get(url)
        self.assertTrue(Trip.objects.filter(pk=self.trip.pk).exists())
        self.assertRedirects(self.client.post(url), self.url('trip_list'))
        self.assertFalse(Trip.objects.exists())
        self.assertFalse(Catch.objects.exists())

    def test_invalid_input_is_not_saved(self):
        for field in ['depth', 'boat_speed']:
            response = self.client.post(self.url('trip_create'), {**self.data, field: '-1'})
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context['form'].errors)
        for field in ['length', 'weight', 'depth']:
            response = self.client.post(self.url('catch_create', self.trip.pk), self.batch({**self.catch_data, field: '-1'}))
            self.assertIn(field, response.context['formset'].forms[0].errors)
        response = self.client.post(self.url('trip_create'), {})
        self.assertIn('lake', response.context['form'].errors)
        self.assertEqual(Trip.objects.count(), 1)
        self.assertEqual(Catch.objects.count(), 1)

    def test_wrong_trip_and_missing_objects(self):
        other = Trip.objects.create(**self.data)
        for name in ['catch_update', 'catch_delete']:
            self.assertEqual(self.client.post(self.url(name, other.pk, self.catch.pk), self.catch_data).status_code, 404)
        self.assertEqual(self.client.get(self.url('trip_detail', 99999)).status_code, 404)

    def test_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url('trip_delete', self.trip.pk)).status_code, 403)
        self.assertEqual(client.post(self.url('trip_create'), self.data).status_code, 403)
        self.assertTrue(Trip.objects.filter(pk=self.trip.pk).exists())

    def test_empty_state_and_pagination(self):
        Trip.objects.all().delete()
        self.assertContains(self.client.get(self.url('home')), 'Ensimmäinen reissu odottaa')
        Trip.objects.bulk_create([Trip(**self.data) for _ in range(13)])
        response = self.client.get(self.url('trip_list'))
        self.assertEqual(len(response.context['trips']), 12)
        self.assertEqual(len(self.client.get(self.url('trip_list') + '?page=2').context['trips']), 1)

    def test_optional_measurements_and_overnight_trip(self):
        data = {**self.data, 'start_time': '22:00', 'end_time': '03:00', 'air_temperature': '', 'water_temperature': '', 'depth': '', 'boat_speed': ''}
        response = self.client.post(self.url('trip_create'), data)
        trip = Trip.objects.latest('pk')
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertIsNone(trip.depth)
        self.assertContains(self.client.get(trip.get_absolute_url()), '+1 vrk')

