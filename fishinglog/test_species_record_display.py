from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Trip, Catch
from .test_catch_batch import trip_data


class SpeciesRecordDisplayTests(TestCase):
    def test_shared_picture_and_trimmed_measurements(self):
        user = get_user_model().objects.create_user('species-display')
        self.client.force_login(user)
        trip = Trip.objects.create(owner=user, **trip_data())
        catch = Catch.objects.create(trip=trip, species='Hauki', weight='10.000', length='2.000', time='12:00', photo='catches/test.jpg')
        response = self.client.get(reverse('fishinglog:statistics'))
        html = response.content.decode().split('Ennätykset lajeittain</h3>', 1)[1].split('Kalapaikat saalismäärän mukaan', 1)[0]
        self.assertEqual(html.count(reverse('fishinglog:catch_photo', args=[catch.pk])), 1)
        self.assertIn('10 <span>kg', html)
        self.assertIn('2 <span>m', html)
        self.assertNotIn('10,000', html)
        self.assertNotIn(trip.location, html)
        self.assertIn('Sama kala', html)
        Catch.objects.create(trip=trip, species='Hauki', weight='9.125', length='2.125', time='13:00', photo='catches/second.jpg')
        response = self.client.get(reverse('fishinglog:statistics'))
        html = response.content.decode().split('Ennätykset lajeittain</h3>', 1)[1].split('Kalapaikat saalismäärän mukaan', 1)[0]
        self.assertEqual(html.count('<img '), 2)
        self.assertIn('2,125 <span>m', html)
        self.assertNotIn('Sama kala', html)

    def test_missing_measurements_and_photos(self):
        user = get_user_model().objects.create_user('species-no-photo')
        self.client.force_login(user)
        trip = Trip.objects.create(owner=user, **trip_data())
        Catch.objects.create(trip=trip, species='Ahven', time='12:00')
        response = self.client.get(reverse('fishinglog:statistics'))
        html = response.content.decode().split('Ennätykset lajeittain</h3>', 1)[1].split('Kalapaikat saalismäärän mukaan', 1)[0]
        self.assertIn('Ei painotietoa', html)
        self.assertIn('Ei pituustietoa', html)
        self.assertNotIn('<img ', html)
