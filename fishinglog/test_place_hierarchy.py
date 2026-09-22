import json
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from . import assistant_location as location, place_hierarchy as hierarchy, geocoding, assistant
from .weather import WeatherError
from .test_assistant import ANSWER

LAKE={'name':'Päijänne','latitude':61.5,'longitude':25.5,'type':'lake',
      'bbox':[61.0,62.5,25.0,26.0],'address':{'state':'Keski-Suomi'},'osm':True}
POINT={'name':'Vaheri','latitude':61.8,'longitude':25.3,'provider':'fmi'}

class HierarchyTests(TestCase):
    @patch('fishinglog.place_hierarchy.geocoding.lookup_all')
    @patch('fishinglog.place_hierarchy.weather.resolve_place')
    def test_both_orders_realistic_fmi_lake_failure_and_multiple_lakes(self,fmi,nomi):
        def resolve(name):
            if name=='vaheri': return POINT.copy()
            raise WeatherError('FMI HTTP 400')
        fmi.side_effect=resolve
        nomi.return_value=[LAKE.copy(),{**LAKE,'latitude':65,'longitude':28,'bbox':[64,66,27,29]}]
        for text in ('Millainen sää Päijänteellä vaherissa huomenna?', 'Millainen sää vaherissa Päijänteellä huomenna?'):
            with self.subTest(text=text):
                result,_,_=location.resolve_request(text,None,'tomorrow',timezone.now())
                self.assertEqual(result['name'],'Vaheri')
                self.assertEqual(result['latitude'],POINT['latitude'])
        self.assertTrue(all(call.args[0].startswith('päijän') for call in nomi.call_args_list))

    @patch('fishinglog.place_hierarchy.candidates')
    def test_administrative_context_selects_compatible_duplicate(self,lookup):
        area={'name':'Jämsä','latitude':61.9,'longitude':25.2,'type':'town','address':{},'bbox':[61.5,62.5,24.5,26]}
        right={**POINT,'type':'pier','address':{'town':'Jämsä'}}
        wrong={**POINT,'latitude':61.7,'type':'isolated_dwelling','address':{'town':'Luhanka'}}
        lookup.side_effect=lambda name,*args: [right,wrong] if name=='vaherissa' else [area]
        self.assertEqual(hierarchy.pair('jämsässä','vaherissa')['type'],'pier')
        self.assertEqual(hierarchy.pair('vaherissa','jämsässä')['type'],'pier')

    @patch('fishinglog.place_hierarchy.candidates')
    def test_lake_context_insufficient_requests_municipality(self,lookup):
        points=[{**POINT,'type':'pier','address':{'town':'Jämsä'}},
                {**POINT,'latitude':61.7,'type':'isolated_dwelling','address':{'town':'Luhanka'}}]
        lookup.side_effect=lambda name,*args: points if name=='vaherissa' else [LAKE]
        with self.assertRaisesRegex(location.PlaceAmbiguity,'kunta'):
            hierarchy.pair('vaherissa','päijänteellä')

    @patch('fishinglog.assistant_location.geocoding.lookup')
    @patch('fishinglog.assistant_location.weather.resolve_place',return_value=POINT)
    def test_single_precise_place_needs_no_area_lookup(self,fmi,nomi):
        result,_,_=location.resolve_request('millainen sää vaherissa huomenna',None,'tomorrow',timezone.now())
        self.assertEqual(result['name'],'Vaheri')
        fmi.assert_called_once_with('vaheri')
        nomi.assert_not_called()

    @patch('fishinglog.place_hierarchy.candidates')
    def test_new_names_not_hardcoded_and_unrelated_area_rejected(self,lookup):
        point={**POINT,'name':'Testikylä','type':'village','address':{'county':'Testialue'}}
        region={**LAKE,'name':'Testialue','type':'county','bbox':[61,63,25,27]}
        lookup.side_effect=lambda name,*args: [point] if name=='testikylässä' else [region]
        self.assertEqual(hierarchy.pair('testialueella','testikylässä')['name'],'Testikylä')
        point['address']={}
        point['latitude']=69
        with self.assertRaises(location.PlaceAmbiguity):
            hierarchy.pair('testikylässä','testialueella')

    @patch('fishinglog.place_hierarchy.candidates')
    def test_warning_contains_only_safe_summary(self,lookup):
        lookup.side_effect=[[{**POINT,'name':'PRIVATE_SENTINEL'}],[LAKE]]
        with self.assertLogs('fishinglog.places',level='WARNING') as logs:
            hierarchy.pair('private_question','secret_area')
        output=' '.join(logs.output)
        self.assertIn('area_context=True',output)
        self.assertIn('candidates=1',output)
        for forbidden in ('PRIVATE_SENTINEL','private_question','secret_area','61.8','25.3'):
            self.assertNotIn(forbidden,output)

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.place_hierarchy.pair',return_value=POINT.copy())
    def test_coordinates_single_ai_and_context_saved(self,pair,forecast,api):
        user=get_user_model().objects.create_user('hierarchy-owner')
        self.client.force_login(user)
        response=self.client.post('/avustaja/',{'question':'Millainen sää Päijänteellä vaherissa huomenna?'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(forecast.call_args.args[:2],('61.8,25.3','tomorrow'))
        api.assert_called_once()
        self.assertEqual(self.client.session['public_weather_context']['name'],'Vaheri')

    @patch('fishinglog.assistant.call_openai')
    @patch('fishinglog.place_hierarchy.pair',side_effect=location.PlaceAmbiguity('Anna tarkemman paikan kunta.'))
    def test_ambiguity_is_form_error_not_server_error(self,pair,api):
        self.client.force_login(get_user_model().objects.create_user('uncertain'))
        response=self.client.post('/avustaja/',{'question':'Päijänteellä Vaherissa huomenna?'})
        self.assertContains(response,'Anna tarkemman paikan kunta.')
        api.assert_not_called()

class CandidateTransportTests(TestCase):
    @patch('fishinglog.geocoding.requests.get')
    def test_preserves_real_response_shape_and_caches_all_candidates(self,get):
        rows=[{'name':'Vaheri','lat':'61.8','lon':'25.3','type':'pier','category':'man_made',
               'address':{'country_code':'fi','town':'Jämsä','municipality':'Jämsän seutukunta','house_number':'PRIVATE'},
               'boundingbox':['61.79','61.81','25.29','25.31']},
              {'name':'Vaheri','lat':'61.7','lon':'25.4','type':'isolated_dwelling',
               'address':{'country_code':'fi','town':'Luhanka'}}]
        response=get.return_value.__enter__.return_value
        response.status_code=200
        response.iter_content.return_value=[json.dumps(rows).encode()]
        result=geocoding.lookup_all('vaheri')
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['address']['town'],'Jämsä')
        self.assertNotIn('house_number',result[0]['address'])
        self.assertEqual(result[0]['type'],'pier')
        self.assertEqual(geocoding.lookup_all('vaheri'),result)
        get.assert_called_once()
