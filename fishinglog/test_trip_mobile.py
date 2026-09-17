from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Trip, FishingSpot
from .test_catch_batch import trip_data

class TripMobileTests(TestCase):
    def test_create_edit_fields_and_private_choices(self):
        user = get_user_model().objects.create_user('mobile')
        other = get_user_model().objects.create_user('other-mobile')
        self.client.force_login(user)
        FishingSpot.objects.create(user=user,name='Oma selkä',latitude=62,longitude=26)
        FishingSpot.objects.create(user=other,name='PRIVATE',latitude=63,longitude=27)
        trip = Trip.objects.create(owner=user, **{**trip_data(),'notes':'Tallennetut muistiinpanot','latitude':62,'longitude':26,'no_catch':True})
        for url in [reverse('fishinglog:trip_create'),reverse('fishinglog:trip_update',args=[trip.pk])]:
            response=self.client.get(url)
            self.assertTemplateUsed(response,'fishinglog/trip_form.html')
            for value in ['Muu paikka','Oma selkä','data-latitude="62.00000"','Lisätiedot','Näytä / muokkaa säätietoja','data-now="start_time"','name="no_catch"']:
                self.assertContains(response,value)
            self.assertNotContains(response,'PRIVATE')
            for field in response.context['form'].fields:
                self.assertContains(response,'name="'+field+'"')
        self.assertContains(response,'Tallennetut muistiinpanot')
        trip.refresh_from_db()
        self.assertTrue(trip.no_catch)
