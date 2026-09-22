from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from . import assistant as ai
from .assistant_places import QUESTION_WORDS, identify_place
from .models import FishingSpot
from .test_assistant import ANSWER


class PlaceParsingTests(SimpleTestCase):
    def test_requested_kyyvesi_forms(self):
        for question in (
            'Monelta huomenna kannattaa lähteä jigaamaan Kyyvedelle?',
            'Milloin Kyyvedellä kannattaa jigata?',
            'Kannattaako huomenna lähteä Kyyvesi-paikalle?',
        ):
            with self.subTest(question=question):
                self.assertEqual(ai.interpret_question(question, ['Kyyvesi'])['place'], 'Kyyvesi')

    def test_question_words_are_never_places(self):
        for word in QUESTION_WORDS:
            with self.subTest(word=word):
                question = f'{word.capitalize()} huomenna kannattaa kalastaa?'
                self.assertEqual(identify_place(question), '')
                self.assertEqual(identify_place(question, [word.capitalize()]), '')

    def test_unclear_prose_does_not_invent_a_place(self):
        for question in ('Huomenna voisi lähteä kalaan', 'Olisipa hyvä sää huomenna!',
                         'Moneltahan kannattaa huomenna lähteä?', 'Onko Jokinpaikka hyvä?'):
            self.assertEqual(identify_place(question), '')

    def test_generalized_known_name_inflections(self):
        for name, form in (('Puulavesi', 'Puulavedellä'), ('Pielisjärvi', 'Pielisjärvelle'),
                           ('Iso saari', 'Isolle saarelle'), ('Syvä lampi', 'Syvä lammella'),
                           ('Jämsä', 'Jämsään')):
            # Multiword adjective inflection is intentionally not guessed.
            expected = '' if form == 'Isolle saarelle' else name
            with self.subTest(name=name):
                self.assertEqual(identify_place(f'Monelta huomenna {form}?', [name]), expected)

    def test_own_names_take_priority_and_boundaries_are_safe(self):
        self.assertEqual(identify_place('Huomenna Kyyvedellä vai Oma selkä?', ['Oma selkä']), 'Oma selkä')
        self.assertEqual(identify_place('Huomenna Iso Kyyvesi?', ['Kyyvesi', 'Iso Kyyvesi']), 'Iso Kyyvesi')
        self.assertEqual(identify_place('Kyyvesikalat', ['Kyyvesi']), '')
        self.assertEqual(identify_place('Huomenna Jämsä vai Puulavesi?', ['Jämsä', 'Puulavesi']), '')


class SavedPlaceRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('place-owner')
        self.other = get_user_model().objects.create_user('another-owner')

    @patch('fishinglog.assistant.call_openai', return_value=ANSWER)
    @patch('fishinglog.assistant.forecast_window', return_value=([], []))
    def test_own_inflected_place_routes_to_coordinates_even_if_old(self, forecast, api):
        spot = FishingSpot.objects.create(user=self.user, name='Kyyvesi', latitude=62, longitude=26)
        FishingSpot.objects.bulk_create([
            FishingSpot(user=self.user, name=f'Muu paikka {i}') for i in range(51)
        ])
        FishingSpot.objects.create(user=self.other, name='Kyyvesi', latitude=64, longitude=28)
        ai.advise(self.user, 'Monelta huomenna kannattaa lähteä jigaamaan Kyyvedelle?')
        forecast.assert_called_once()
        self.assertEqual(forecast.call_args.args[:2], ('62.00000,26.00000', 'tomorrow'))
        api.assert_called_once()
        payload = api.call_args.args[1]
        self.assertEqual(payload['plan']['place'], 'Kyyvesi')
        self.assertEqual(payload['saved_spots']['places'][0]['spot_id'], spot.pk)
        self.assertTrue(all(p['name'] != 'Kyyvesi' or p['spot_id'] == spot.pk
                            for p in payload['saved_spots']['places']))

    @patch('fishinglog.assistant.call_openai')
    @patch('fishinglog.assistant.forecast_window')
    @patch('fishinglog.assistant_location.resolve', return_value=None)
    def test_foreign_or_missing_place_is_not_guessed(self, resolve, forecast, api):
        FishingSpot.objects.create(user=self.other, name='Salajärvi', latitude=64, longitude=28)
        for question in ('Monelta huomenna kannattaa lähteä?', 'Monelta huomenna Salajärvelle?'):
            with self.subTest(question=question), self.assertRaises(ai.AssistantError):
                ai.advise(self.user, question)
        forecast.assert_not_called()
        api.assert_not_called()
