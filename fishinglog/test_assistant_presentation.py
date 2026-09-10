from django.test import SimpleTestCase
from django.template.loader import render_to_string
from .assistant_presentation import answer_summary


class AssistantPresentationTests(SimpleTestCase):
    def test_scores_and_missing_values(self):
        for score, label in [(1,'Heikko'),(3,'Heikko'),(4,'Kohtalainen'),(6,'Kohtalainen'),(7,'Hyvä'),(8,'Hyvä'),(9,'Erinomainen'),(10,'Erinomainen'),(None,'Ei arvioitu'),('7','Ei arvioitu')]:
            self.assertEqual(answer_summary({'answer': {'score':score}})['label'], label)

    def test_legacy_and_escaped_answers(self):
        for result in ({'answer':{}}, {'answer':{'score':7,'recommendation':'<script>alert(1)</script>', 'rationale':'Vanha vastaus'}}):
            html = render_to_string('fishinglog/assistant.html', {'result': result, 'summary':answer_summary(result), 'api_key_configured':True})
            self.assertIn('Datapohja',html)
            self.assertIn('Suositus',html)
            self.assertNotIn('<script>alert(1)</script>',html)
            if result['answer'].get('score'):
                self.assertIn('7/10',html)
                self.assertIn('aria-valuenow="7"',html)

    def test_rationale_sections(self):
        summary = answer_summary({'answer':{'rationale':'Oma historia: Vähän dataa. Sääennuste: Tuulta. Oma arvio: Varovainen.'}})
        self.assertEqual([item['title'] for item in summary['sections']], ['Oma historia','Sääennuste','Oma arvio'])

    def test_place_only_recommendation_uses_existing_fields(self):
        result = {'place':'Kyyvesi', 'answer':{'recommendation':'Kyyvesi', 'best_time':'Huomenna 18–21', 'species':'Kuha', 'method':'Jiggaus'}, 'spot_history_summary':[{'name':'Kyyvesi','included_trips':2,'total_trips':2},{'name':'Tuokkari','included_trips':1,'total_trips':1}]}
        summary = answer_summary(result)
        for value in ('Kyyvesi', 'Huomenna 18–21', 'Kuha', 'Jiggaus'):
            self.assertIn(value, summary['recommendation'])
        self.assertNotIn('Viehe',summary['recommendation'])
        self.assertEqual([row['recommended'] for row in summary['comparison']], [True, False])
        html = render_to_string('fishinglog/assistant.html', {'result':result,'summary':summary,'api_key_configured':True})
        self.assertIn('Vertailussa käytetyt kalapaikat',html)
        self.assertEqual(html.count('Suositeltu paikka'),1)

    def test_actual_recommendation_and_warnings_preserved(self):
        text = 'Älä lähde tänään; tuuli on liian voimakas.'
        self.assertEqual(answer_summary({'answer':{'recommendation':text}})['recommendation'],text)
        summary = answer_summary({'warning':'Sää puuttuu','answer':{'recommendation':'Kyyvesi'},'spot_history_summary':[{'name':'Kyyvesi'}]})
        self.assertFalse(summary['comparison'][0]['recommended'])

    def test_missing_recommendation_and_unknown_winner(self):
        summary = answer_summary({'place':'Omat kalapaikat','answer':{'species':'Ahven'},'spot_history_summary':[{'name':'Testipaikka'}]})
        self.assertIn('Ahven',summary['recommendation'])
        self.assertFalse(summary['comparison'][0]['recommended'])
        self.assertNotIn('Viehe',summary['recommendation'])
