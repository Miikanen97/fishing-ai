import copy
import json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Trip, Catch, FishingSpot
from .test_catch_batch import trip_data
from .test_assistant import ANSWER
from .assistant import advise, AssistantError
from .assistant_privacy import private_payload


class OutboundPrivacyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('privacy-owner')
        other = get_user_model().objects.create_user('privacy-other')
        self.spot = FishingSpot.objects.create(user=self.user, name='Oma selkä', latitude='62.12345', longitude='26.54321', notes='PRIVATE_NOTE')
        self.trip = Trip.objects.create(owner=self.user, fishing_spot=self.spot, notes='TRIP_NOTE', **trip_data())
        Catch.objects.create(trip=self.trip, species='Kuha', time='12:00', notes='CATCH_NOTE')
        FishingSpot.objects.create(user=other, name='FOREIGN_SPOT', notes='FOREIGN_NOTE', latitude=65, longitude=28)

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([{'target':'tomorrow', 'source':'FMI (62.12345, 26.54321)', 'values':{'weather_latitude':'62.12345', 'weather_longitude':'26.54321', 'air_temperature':12}}], []))
    def test_weather_internal_coordinates_but_outbound_private(self, forecast, api):
        advise(self.user, 'Kannattaako huomenna mennä Oma selkä?')
        self.assertEqual(forecast.call_args.args[0], '62.12345,26.54321')
        api.assert_called_once()
        payload = api.call_args.args[1]
        text = json.dumps(payload, default=str)
        for secret in ('62.12345', '26.54321', 'PRIVATE_NOTE', 'TRIP_NOTE', 'CATCH_NOTE', 'FOREIGN'):
            self.assertNotIn(secret, text)
        self.assertEqual(payload['weather'][0]['values']['air_temperature'],12)
        self.assertIn('Kuha',text)

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    def test_notes_explicit_and_one_owned_place_only(self, api):
        FishingSpot.objects.create(user=self.user, name='Toinen', notes='UNSELECTED_NOTE')
        advise(self.user, 'Vertaa reissujani', selected_place=self.spot.name, include_notes=True)
        text=json.dumps(api.call_args.args[1],default=str)
        for note in ('PRIVATE_NOTE','TRIP_NOTE','CATCH_NOTE'):
            self.assertIn(note,text)
        for secret in ('UNSELECTED_NOTE','FOREIGN','62.12345','26.54321'):
            self.assertNotIn(secret,text)
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai')
    def test_notes_require_owned_selection(self, api):
        for place in ('','FOREIGN_SPOT'):
            with self.assertRaises(AssistantError):
                advise(self.user,'Vertaa reissujani',selected_place=place,include_notes=True)
        api.assert_not_called()

    def test_copy_budget_nested_coordinates_and_default(self):
        payload={'place':'62.12345,26.54321','saved_spots':{'places':[{'spot_id':1,'notes':'N'*500,'history':[{'notes':'N'*500} for _ in range(20)]}]}}
        original=copy.deepcopy(payload)
        result=private_payload(payload,notes_spot=1)
        self.assertEqual(sum(len(r.get('notes','')) for r in result['saved_spots']['places'][0]['history'])+len(result['saved_spots']['places'][0]['notes']),2000)
        self.assertEqual(payload,original)
        self.assertNotIn('"notes":',json.dumps(private_payload(payload)))

    @patch('fishinglog.assistant_views.advise', return_value=None)
    def test_consent_is_per_submission(self, api):
        self.client.force_login(self.user)
        url=reverse('fishinglog:assistant')
        self.client.post(url,{'question':'Vertaa reissujani','place':self.spot.name,'include_notes':'on'})
        self.assertTrue(api.call_args.kwargs['include_notes'])
        self.client.post(url,{'question':'Vertaa reissujani','place':self.spot.name})
        self.assertFalse(api.call_args.kwargs['include_notes'])
