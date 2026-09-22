import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
import requests
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from . import geocoding, assistant_location as location, assistant as ai
from .assistant_places import identify_place
from .models import FishingSpot, GeocodingGate
from .weather import WeatherError
from .test_assistant import ANSWER

AREA = {'name': 'Päijänne', 'latitude': 61.5, 'longitude': 25.5}
LOCAL = {'name': 'Vaheri', 'latitude': 61.8, 'longitude': 25.3, 'osm': True}


class PublicParserTests(SimpleTestCase):
    def test_inflections_and_compound_places(self):
        for name in ('Päijänne','Päijänteellä','Päijänteelle','Päijänteeltä'):
            self.assertEqual(identify_place(f'Millainen sää {name} huomenna?', ['Päijänne']), 'Päijänne')
        for text in ('Vaheri Päijänteellä','Vaheri Päijänne'):
            self.assertEqual(tuple(location.candidate_name(v) for v in location.public_candidate(text)[:2]), ('Vaheri','Päijänne'))
        self.assertEqual(identify_place('Huomenna Länsijänteellä', ['Länsijänne']), 'Länsijänne')

    @patch('fishinglog.assistant_location.resolve')
    def test_refinement_and_explicit_fallback(self, resolve):
        now = timezone.now()
        previous = {**AREA,'period':'tomorrow','updated':now.timestamp()}
        resolve.return_value = LOCAL.copy()
        result, notice, period = location.resolve_request('Entäs Vaherissa?', previous, 'clarify', now)
        self.assertEqual((result['name'],period,notice), ('Vaheri','tomorrow',''))
        resolve.assert_called_once_with('Vaherissa',previous)
        resolve.return_value = None
        result, notice, period = location.resolve_request('Vaheri', previous, 'clarify', now)
        self.assertEqual(result['name'],'Päijänne')
        self.assertIn('laajempaan alueeseen',notice)
        result, notice, _ = location.resolve_request('Huomenna Helsingissä?', previous, 'tomorrow',now)
        self.assertIsNone(result)
        self.assertEqual(notice,'')

    @patch('fishinglog.assistant_location.geocoding.lookup')
    @patch('fishinglog.assistant_location.weather.resolve_place')
    def test_fmi_first_and_mismatching_fmi_fallback(self, fmi, lookup):
        fmi.return_value = LOCAL
        self.assertEqual(location.resolve('Vaheri',AREA)['name'],'Vaheri')
        lookup.assert_not_called()
        lookup.return_value = None
        fmi.return_value = {'name':'Muu','latitude':68,'longitude':26}
        location.resolve('Vaheri',AREA)
        lookup.assert_called_once_with('vaheri',AREA)

    def test_context_expiry_and_whitelist(self):
        now=timezone.now()
        data={**AREA,'period':'tomorrow','updated':now.timestamp(),'notes':'secret'}
        self.assertNotIn('notes',location.context(data,now))
        data['updated']-=21601
        self.assertIsNone(location.context(data,now))


class GeocodingTests(TestCase):
    def response(self, get, rows):
        response=get.return_value.__enter__.return_value
        response.status_code=200
        response.iter_content.return_value=[json.dumps(rows).encode()]

    def row(self, **kwargs):
        return {'name':'Vaheri','lat':'61.8','lon':'25.3','address':{'country_code':'fi'},**kwargs}

    @patch('fishinglog.geocoding.requests.get')
    def test_success_country_bounds_headers_cache_and_no_private_payload(self,get):
        self.response(get,[self.row()])
        self.assertEqual(geocoding.lookup('Vaheri',AREA)['name'],'Vaheri')
        self.assertEqual(geocoding.lookup('Vaheri',AREA)['name'],'Vaheri')
        get.assert_called_once()
        args=get.call_args.kwargs
        self.assertEqual(args['params']['q'],'Vaheri')
        self.assertEqual(args['params']['countrycodes'],'fi')
        self.assertTrue(args['params']['bounded'])
        self.assertIn('FishingAI',args['headers']['User-Agent'])
        self.assertEqual(args['timeout'],(3,5))

    @patch('fishinglog.geocoding.requests.get')
    def test_ambiguous_wrong_region_wrong_country_and_missing(self,get):
        for rows in ([self.row(),self.row(lat='61.9')], [self.row(lat='69')],
                     [self.row(address={'country_code':'se'})], [], [self.row(name='Other')]):
            with self.subTest(rows=rows):
                from .models import PublicGeocodingCache
                PublicGeocodingCache.objects.all().delete()
                GeocodingGate.objects.all().delete()
                self.response(get,rows)
                if len(rows) > 1:
                    with self.assertRaises(geocoding.AmbiguousGeocoding):
                        geocoding.lookup('Vaheri',AREA)
                else:
                    self.assertIsNone(geocoding.lookup('Vaheri',AREA))

    @patch('fishinglog.geocoding.requests.get',side_effect=requests.Timeout('secret-url'))
    def test_timeout_safe(self,get):
        self.assertIsNone(geocoding.lookup('Vaheri'))
        get.assert_called_once()

    @patch('fishinglog.geocoding.requests.get')
    def test_shared_busy_gate_prevents_request(self,get):
        GeocodingGate.objects.create(pk=1,next_allowed=timezone.now()+timedelta(seconds=20))
        self.assertIsNone(geocoding.lookup('Vaheri'))
        get.assert_not_called()

    @patch('fishinglog.geocoding.requests.get')
    def test_negative_result_cached(self,get):
        self.response(get,[])
        self.assertIsNone(geocoding.lookup('Vaheri'))
        self.assertIsNone(geocoding.lookup('Vaheri'))
        get.assert_called_once()


class LocationIntegrationTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('public-location')
        self.client.force_login(self.user)

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.assistant_location.resolve')
    def test_session_followup_forecast_coordinates_and_one_ai_per_submission(self,resolve,forecast,api):
        resolve.side_effect=[AREA.copy(),LOCAL.copy()]
        first=self.client.post('/avustaja/',{'question':'Millainen sää Päijänteellä huomenna?'})
        self.assertEqual(first.status_code,200)
        self.assertEqual(self.client.session['public_weather_context']['name'],'Päijänne')
        second=self.client.post('/avustaja/',{'question':'Vaheri'})
        self.assertEqual(second.status_code,200)
        self.assertEqual(forecast.call_args.args[:2],('61.8,25.3','tomorrow'))
        self.assertEqual(api.call_count,2)
        self.assertEqual(self.client.session['public_weather_context']['name'],'Vaheri')
        self.assertContains(second,'OpenStreetMap contributors')

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.geocoding.lookup')
    def test_private_spots_skip_public_resolution_and_clear_session(self,lookup,forecast,api):
        FishingSpot.objects.create(user=self.user,name='Päijänne',latitude=62,longitude=26,notes='PRIVATE')
        other=get_user_model().objects.create_user('other-public-location')
        FishingSpot.objects.create(user=other,name='Päijänne',latitude=65,longitude=28)
        response=self.client.post('/avustaja/',{'question':'Huomenna Päijänteellä?'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(forecast.call_args.args[0],'62.00000,26.00000')
        lookup.assert_not_called()
        self.assertNotIn('public_weather_context',self.client.session)
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.assistant_location.resolve')
    def test_compound_uses_small_locality_and_fallback_is_visible(self,resolve,forecast,api):
        resolve.side_effect=[AREA.copy(),LOCAL.copy()]
        self.client.post('/avustaja/',{'question':'Huomenna Vaheri Päijänteellä?'})
        self.assertEqual(forecast.call_args.args[0],'61.8,25.3')
        resolve.side_effect=None
        resolve.return_value=None
        response=self.client.post('/avustaja/',{'question':'Entäs Muualla?'})
        self.assertContains(response,'Tarkkaa paikkaa ei löytynyt varmasti')
        self.assertEqual(api.call_count,2)

class FullFallbackTests(TestCase):
    @patch('fishinglog.assistant.call_openai',return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window',return_value=([],[]))
    @patch('fishinglog.assistant_location.weather.resolve_place')
    @patch('fishinglog.geocoding.requests.get')
    def test_fmi_name_failure_geocodes_then_forecasts_by_coordinates(self,get,fmi,forecast,api):
        user=get_user_model().objects.create_user('fallback-owner')
        def fmi_result(name):
            if name.startswith('päijän'):
                return AREA.copy()
            raise WeatherError('not found')
        fmi.side_effect=fmi_result
        response=get.return_value.__enter__.return_value
        response.status_code=200
        response.iter_content.return_value=[json.dumps([{
            'name':'Vaheri','lat':'61.8','lon':'25.3','address':{'country_code':'fi'}
        }]).encode()]
        result=ai.advise(user,'Huomenna Vaheri Päijänteellä?')
        self.assertEqual(result['place'],'Vaheri')
        forecast.assert_called_once()
        self.assertEqual(forecast.call_args.args[:2],('61.8,25.3','tomorrow'))
        self.assertEqual(get.call_args.kwargs['params']['q'],'vaheri')
        get.assert_called_once()
        api.assert_called_once()

    @patch('fishinglog.assistant.call_openai')
    @patch('fishinglog.assistant_location.resolve',return_value=None)
    def test_failed_independent_place_does_not_use_previous_or_call_ai(self,resolve,api):
        user=get_user_model().objects.create_user('failed-owner')
        with self.assertRaises(ai.AssistantError):
            ai.advise(user,'Huomenna Helsingissä?', public_context={
                **AREA,'period':'tomorrow','updated':timezone.now().timestamp()})
        api.assert_not_called()

    @patch('fishinglog.geocoding.requests.get')
    def test_http_error_malformed_and_oversized_responses(self,get):
        response=get.return_value.__enter__.return_value
        for status,body in ((429,b'private error body'),(200,b'not json'),(200,b'x'*100001)):
            with self.subTest(status=status,size=len(body)):
                GeocodingGate.objects.all().delete()
                response.status_code=status
                response.iter_content.return_value=[body]
                self.assertIsNone(geocoding.lookup('Vaheri'))

    def test_other_lake_inflection_is_generic(self):
        self.assertEqual(tuple(location.candidate_name(v) for v in location.public_candidate('Huomenna Niemi Puulavedellä?')[:2]),('Niemi','Puulavesi'))

class GeneralPlaceResolutionTests(SimpleTestCase):
    @patch('fishinglog.assistant_location.geocoding.lookup',return_value=None)
    @patch('fishinglog.assistant_location.weather.resolve_place')
    def test_general_inflections_require_provider_confirmation(self,fmi,nomi):
        examples = {
            'Päijänne': ['Päijänteellä','Päijänteelle','Päijänteeltä'],
            'Kyyvesi': ['Kyyvedellä','Kyyvedelle','Kyyvedeltä'],
            'Puula': ['Puulalla','Puulalle','Puulalta'],
            'Keitele': ['Keiteleellä','Keiteleelle','Keiteleeltä'],
            'Vaheri': ['Vaherissa','Vaheriin','vaherissa'],
            'Nuottala': ['nuottalassa','Nuottalaan'],
            'Kivile': ['Kivileellä','kivileelle'],
        }
        for base,variants in examples.items():
            def response(candidate):
                if candidate == base.casefold():
                    return {'name':base,'latitude':62,'longitude':26}
                raise WeatherError('not found')
            fmi.side_effect=response
            for word in variants:
                with self.subTest(word=word):
                    candidate=location.public_candidate(f'millainen sää {word} huomenna')[0]
                    self.assertEqual(candidate,word)
                    result=location.resolve(candidate)
                    self.assertEqual(result['name'],base)
                    self.assertLessEqual(len(location.name_candidates(word)),3)
        nomi.assert_not_called()

    @patch('fishinglog.assistant_location.geocoding.lookup',return_value=None)
    @patch('fishinglog.assistant_location.weather.resolve_place')
    def test_wrong_canonical_name_and_unconfirmed_candidates_rejected(self,fmi,nomi):
        fmi.return_value={'name':'Toinen paikka','latitude':62,'longitude':26}
        self.assertIsNone(location.resolve('Keiteleellä'))
        self.assertLessEqual(fmi.call_count,3)
        self.assertLessEqual(nomi.call_count,3)
        fmi.side_effect=WeatherError('not found')
        self.assertIsNone(location.resolve('Nuottalassa'))

    @patch('fishinglog.assistant_location.geocoding.lookup')
    @patch('fishinglog.assistant_location.weather.resolve_place')
    def test_two_verified_stem_alternatives_are_ambiguous(self,fmi,nomi):
        def response(candidate):
            return {'name':candidate.capitalize(),'latitude':62,'longitude':26}
        fmi.side_effect=response
        self.assertIsNone(location.resolve('Keiteleellä'))
        nomi.assert_not_called()

    @patch('fishinglog.assistant_location.geocoding.lookup')
    @patch('fishinglog.assistant_location.weather.resolve_place',side_effect=WeatherError('not found'))
    def test_unknown_lowercase_name_nominatim_confirmation(self,fmi,nomi):
        nomi.side_effect=lambda name,area: {'name':'Nuottala','latitude':62,'longitude':26,'osm':True} if name=='nuottala' else None
        result=location.resolve('nuottalassa',AREA)
        self.assertEqual(result['name'],'Nuottala')
        nomi.assert_called_once_with('nuottala',AREA)

    def test_question_words_and_ordinary_words_never_become_places(self):
        from .assistant_places import QUESTION_WORDS
        for word in QUESTION_WORDS:
            with self.subTest(word=word):
                self.assertEqual(location.public_candidate(f'{word} huomenna kannattaa lähteä kalaan?')[0],'')
        for question in ('Monelta huomenna?', 'millainen sää huomenna', 'Kannattaako huomenna uistella kuhaa?'):
            self.assertEqual(location.public_candidate(question)[0],'')
        with self.assertRaises(location.PlaceAmbiguity):
            location.public_candidate('Huomenna Puulalla vai Keiteleellä?')

    def test_own_places_support_long_e_and_illative(self):
        for question,name in (('keiteleellä','Keitele'),('Keiteleelle','Keitele'),('Vaheriin','Vaheri')):
            self.assertEqual(identify_place(question,[name]),name)
        self.assertEqual(identify_place('Päijänteellä'), '')  # No hardcoded public-name registry.

    @patch('fishinglog.assistant_location.geocoding.lookup',return_value=None)
    @patch('fishinglog.assistant_location.weather.resolve_place')
    def test_public_context_followup_uses_area_and_lowercase(self,fmi,nomi):
        def response(candidate):
            if candidate=='päijänne': return AREA.copy()
            if candidate=='vaheri': return LOCAL.copy()
            raise WeatherError('missing')
        fmi.side_effect=response
        now=timezone.now()
        first,_,_=location.resolve_request('millainen sää päijänteellä huomenna',None,'tomorrow',now)
        second,notice,period=location.resolve_request('vaherissa',first,'clarify',now)
        self.assertEqual((second['name'],period,notice),('Vaheri','tomorrow',''))
        fmi.side_effect=None
        fmi.return_value={'name':'Vaheri','latitude':69,'longitude':26}
        fallback,notice,_=location.resolve_request('Entäs Vaherissa?',first,'clarify',now)
        self.assertEqual(fallback['name'],'Päijänne')
        self.assertIn('laajempaan alueeseen',notice)

    @patch('fishinglog.assistant_location.geocoding.lookup',side_effect=geocoding.AmbiguousGeocoding('multiple'))
    @patch('fishinglog.assistant_location.weather.resolve_place',side_effect=WeatherError('missing'))
    def test_nominatim_ambiguity_cannot_be_overridden_by_another_spelling(self,fmi,nomi):
        self.assertIsNone(location.resolve('Keiteleellä'))
        nomi.assert_called_once()

    @patch('fishinglog.assistant_location.geocoding.lookup')
    @patch('fishinglog.assistant_location.weather.resolve_place')
    @patch('fishinglog.assistant_location.time.monotonic',return_value=100)
    def test_resolution_budget_fails_closed(self,clock,fmi,nomi):
        token=location.RESOLUTION_DEADLINE.set(99)
        try:
            self.assertIsNone(location.resolve('Keiteleellä'))
        finally:
            location.RESOLUTION_DEADLINE.reset(token)
        fmi.assert_not_called()
        nomi.assert_not_called()
