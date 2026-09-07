from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from .models import Trip
from .forms import TripForm
from .test_catch_batch import trip_data
from .test_weather import TARGET


class MapTests(TestCase):
    def test_form_and_detail_maps_and_zero_coordinates(self):
        data = {**trip_data(), 'latitude': '0', 'longitude': '0', 'weather_latitude': '62.1', 'weather_longitude': '26.1'}
        response = self.client.post(reverse('fishinglog:trip_create'), data)
        trip = Trip.objects.get()
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.latitude, Decimal('0'))
        self.assertEqual(trip.weather_latitude, Decimal('62.1'))
        detail = self.client.get(trip.get_absolute_url())
        self.assertContains(detail, 'data-latitude="0.00000"')
        self.assertContains(detail, 'Avaa kartalla')
        self.assertContains(detail, 'mlat=0.00000')
        edit = self.client.get(reverse('fishinglog:trip_update', args=[trip.pk]))
        self.assertContains(edit, 'Käytä nykyistä sijaintiani')
        self.assertContains(edit, 'leaflet/leaflet.js')
        self.assertContains(edit, 'name="latitude" value="0.00000"')
        self.client.post(reverse('fishinglog:trip_update', args=[trip.pk]), {**data,'latitude':'61.12345','longitude':'27.45678'})
        trip.refresh_from_db()
        self.assertEqual(trip.longitude, Decimal('27.45678'))
        self.assertEqual(trip.weather_latitude, Decimal('62.1'))

    def test_no_gps_does_not_show_weather_location_as_marker(self):
        trip = Trip.objects.create(**trip_data(), weather_latitude='62.1', weather_longitude='26.1')
        response = self.client.get(trip.get_absolute_url())
        self.assertNotContains(response, 'id="fishing-map"')
        self.assertContains(response, 'Tarkkaa kalastuspaikkaa ei ole valittu')

    def test_coordinate_pair_validation_and_removal(self):
        for extra in [{'latitude':'62'}, {'longitude':'26'}, {'latitude':'91','longitude':'26'}]:
            self.assertFalse(TripForm({**trip_data(), **extra}).is_valid())
        self.assertTrue(TripForm(trip_data()).is_valid())

    @patch('fishinglog.views.fetch_weather', return_value={'values':{}})
    def test_weather_uses_gps_before_name(self, weather):
        response = self.client.post(reverse('fishinglog:weather_lookup'),
             {'date':'2024-06-01','time':'12:00','place':'Jyväskylä','latitude':'61.12345','longitude':'27.45678'})
        self.assertEqual(response.status_code,200)
        weather.assert_called_once_with('61.12345,27.45678', TARGET)

    @patch('fishinglog.views.fetch_weather', return_value={'values':{}})
    def test_weather_can_use_coordinates_without_name(self, weather):
        response = self.client.post(reverse('fishinglog:weather_lookup'),
             {'date':'2024-06-01','time':'12:00','latitude':'0','longitude':'0'})
        self.assertEqual(response.status_code,200)
        weather.assert_called_once_with('0,0',TARGET)

    @patch('fishinglog.views.fetch_weather')
    def test_partial_gps_does_not_silently_fall_back(self, weather):
        response = self.client.post(reverse('fishinglog:weather_lookup'),
             {'date':'2024-06-01','time':'12:00','place':'Kyyvesi','latitude':'62'})
        self.assertEqual(response.status_code,400)
        weather.assert_not_called()


class CoordinateMigrationTests(TransactionTestCase):
    def test_old_coordinates_move_to_weather_fields_without_inventing_gps(self):
        old = [('fishinglog','0004_trip_latitude_trip_longitude_trip_wind_gust')]
        new = [('fishinglog','0005_separate_fishing_coordinates')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            model = executor.loader.project_state(old).apps.get_model('fishinglog','Trip')
            trip = model.objects.create(**trip_data(), latitude='61.99757', longitude='27.16802', weather_source='FMI station',weather_place='Kyyvesi')
            executor = MigrationExecutor(connection); executor.migrate(new)
            model = executor.loader.project_state(new).apps.get_model('fishinglog','Trip')
            trip = model.objects.get(pk=trip.pk)
            self.assertIsNone(trip.latitude); self.assertIsNone(trip.longitude)
            self.assertEqual(trip.weather_latitude, Decimal('61.99757'))
            self.assertEqual(trip.weather_longitude, Decimal('27.16802'))
            self.assertEqual(trip.weather_source,'FMI station')
            self.assertEqual(trip.weather_place,'Kyyvesi')
        finally:
            executor = MigrationExecutor(connection); executor.migrate(executor.loader.graph.leaf_nodes())

