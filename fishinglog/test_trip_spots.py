from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Trip, Catch, FishingSpot
from .forms import TripForm


class TripSpotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('trip-spot-owner')
        self.other = get_user_model().objects.create_user('foreign-owner')
        self.client.force_login(self.user)
        self.spot = FishingSpot.objects.create(pk=1234, user=self.user, name='Oma kalapaikka', latitude=62, longitude=26)
        self.foreign = FishingSpot.objects.create(user=self.other, name='Salainen paikka', latitude=61, longitude=25)
        self.data = dict(date='2026-09-10', lake='Kyyvesi', location='Vanha nimi', start_time='08:00', end_time='12:00', fishing_method='Jiggaus')
        self.create_url = reverse('fishinglog:trip_create')

    def test_own_choices_create_and_map_link(self):
        response = self.client.get(self.create_url)
        self.assertContains(response, 'Muu paikka')
        self.assertContains(response, self.spot.name)
        self.assertNotContains(response, self.foreign.name)
        response = self.client.post(self.create_url, {**self.data, 'location': '', 'fishing_spot': self.spot.pk})
        trip = Trip.objects.get(owner=self.user)
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.fishing_spot, self.spot)
        self.assertEqual(trip.location, self.spot.name)
        self.assertContains(self.client.get(trip.get_absolute_url()), reverse('fishinglog:spots') + '?spot=' + str(self.spot.pk))
        self.assertContains(self.client.get(reverse('fishinglog:trip_update', args=[trip.pk])), f'value="{self.spot.pk}" selected')

    def test_foreign_post_rejected_on_create_and_update(self):
        response = self.client.post(self.create_url, {**self.data, 'fishing_spot': self.foreign.pk})
        self.assertIn('fishing_spot', response.context['form'].errors)
        self.assertFalse(Trip.objects.exists())
        trip = Trip.objects.create(owner=self.user, **self.data)
        response = self.client.post(reverse('fishinglog:trip_update', args=[trip.pk]), {**self.data, 'fishing_spot': self.foreign.pk})
        self.assertIn('fishing_spot', response.context['form'].errors)
        trip.refresh_from_db()
        self.assertIsNone(trip.fishing_spot)
        self.assertEqual(trip.location, 'Vanha nimi')
        self.assertFalse(TripForm().fields['fishing_spot'].queryset.exists())

    def test_existing_trip_attach_detach_and_delete_preserves_history(self):
        trip = Trip.objects.create(owner=self.user, **self.data)
        catch = Catch.objects.create(trip=trip, species='Hauki', time='09:00')
        update = reverse('fishinglog:trip_update', args=[trip.pk])
        self.assertRedirects(self.client.post(update, {**self.data, 'fishing_spot': self.spot.pk}), trip.get_absolute_url())
        self.spot.name = 'Uusi nimi'
        self.spot.save()
        self.client.post(update, {**self.data, 'fishing_spot': self.spot.pk})
        trip.refresh_from_db()
        self.assertEqual(trip.location, 'Uusi nimi')
        self.client.post(update, {**self.data, 'fishing_spot': '', 'location': 'Muu selkä'})
        trip.refresh_from_db()
        self.assertIsNone(trip.fishing_spot)
        self.assertEqual(trip.location, 'Muu selkä')
        self.client.post(update, {**self.data, 'fishing_spot': self.spot.pk})
        self.spot.delete()
        trip.refresh_from_db()
        self.assertIsNone(trip.fishing_spot)
        self.assertEqual(trip.location, 'Uusi nimi')
        self.assertTrue(Catch.objects.filter(pk=catch.pk, trip=trip).exists())
        self.assertEqual(self.client.get(trip.get_absolute_url()).status_code, 200)

    def test_other_place_requires_text_and_legacy_post_works(self):
        response = self.client.post(self.create_url, {**self.data, 'location': ''})
        self.assertIn('location', response.context['form'].errors)
        self.client.post(self.create_url, self.data)
        trip = Trip.objects.get()
        self.assertIsNone(trip.fishing_spot)
        self.assertEqual(trip.location, 'Vanha nimi')

    def test_choices_on_create_edit_and_invalid_post(self):
        trip = Trip.objects.create(owner=self.user, **self.data)
        for url in (self.create_url, reverse('fishinglog:trip_update', args=[trip.pk])):
            for method in ('get', 'post'):
                response = getattr(self.client, method)(url)
                self.assertEqual(list(response.context['form'].fields['fishing_spot'].queryset), [self.spot])
                self.assertContains(response, self.spot.name)
                self.assertNotContains(response, self.foreign.name)

    def test_map_payload_is_owner_scoped_for_every_requested_id(self):
        for spot_id in ('', 'invalid', str(self.foreign.pk), str(self.spot.pk)):
            response = self.client.get(reverse('fishinglog:spots'), {'spot': spot_id})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([item['id'] for item in response.context['spots']], [self.spot.pk])
            self.assertNotContains(response, self.foreign.name)

    def test_save_new_place_with_and_without_coordinates_and_reuse(self):
        for coordinates in ({}, {'latitude': '63.12345', 'longitude': '27.12345'}):
            name = 'Uusi paikka ' + str(len(coordinates))
            payload = {**self.data, **coordinates, 'location': name, 'save_spot': 'on'}
            self.client.post(self.create_url, payload)
            trip = Trip.objects.latest('pk')
            spot = trip.fishing_spot
            self.assertIsNotNone(spot)
            self.assertEqual(spot.user, self.user)
            self.assertEqual(spot.name, name)
            response = self.client.get(reverse('fishinglog:spots'))
            self.assertContains(response, name)
            if not coordinates:
                self.assertIsNone(spot.latitude)
                self.assertContains(response, 'Karttasijainti puuttuu')
            count = FishingSpot.objects.count()
            self.client.post(self.create_url, payload)
            self.assertEqual(FishingSpot.objects.count(), count)
            self.assertEqual(Trip.objects.latest('pk').fishing_spot, spot)

    def test_existing_coordinates_and_no_accidental_creation(self):
        self.client.post(self.create_url, {**self.data, 'fishing_spot': self.spot.pk})
        trip = Trip.objects.latest('pk')
        self.assertEqual((trip.latitude, trip.longitude), (self.spot.latitude, self.spot.longitude))
        count = FishingSpot.objects.count()
        self.client.post(self.create_url, {**self.data, 'save_spot': 'on', 'latitude': '62', 'longitude': '26'})
        self.assertEqual(FishingSpot.objects.count(), count)
        self.assertEqual(Trip.objects.latest('pk').fishing_spot, self.spot)
        self.client.post(self.create_url, self.data)
        self.assertEqual(FishingSpot.objects.count(), count)
        self.assertIsNone(Trip.objects.latest('pk').fishing_spot)

    def test_trip_list_create_button(self):
        response = self.client.get(reverse('fishinglog:trip_list'))
        self.assertContains(response, '+ Lisää uusi reissu')
        self.assertContains(response, f'href="{self.create_url}"')
