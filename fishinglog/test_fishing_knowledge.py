"""Synthetic validation fixtures only; not fishing advice or production content."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from django.core.management import call_command
from django.test import SimpleTestCase
from .fishing_knowledge import (KNOWLEDGE_DIR, KnowledgeValidationError,
                               load_knowledge, validate_bundle, active_rules)


def fixture_rule():
    return {'id':'test_fixture','version':1,'status':'draft','species':['kuha'],
            'when':{},'requires':[], 'recommend':{'lure_types':['jig']},
            'reason_fi':'TEST ONLY: synthetic schema fixture, not fishing advice.',
            'evidence_type':'research','source_ids':[],'unknown_policy':'skip',
            'conflict_group':'lure_type'}


def fixture_source():
    return {'id':'fixture_source','title':'TEST ONLY','publisher':'Test fixture',
            'url':'https://example.invalid/test-fixture','accessed_on':'2026-01-01',
            'evidence_type':'research','scope_fi':'Synthetic validation fixture',
            'locator':'test fixture, no actual fishing information'}


class KnowledgeTests(SimpleTestCase):
    def setUp(self):
        self.bundle=load_knowledge()
        self.rules=next(d['rules'] for d in self.bundle['rule_files'] if d['scope']=='kuha')
        self.rule=fixture_rule()
        self.rules.append(self.rule)

    def approve(self):
        self.bundle['sources']['sources'].append(fixture_source())
        self.rule.update(status='approved',source_ids=['fixture_source'])

    def test_production_files_validate_and_contain_no_advice(self):
        bundle=load_knowledge()
        validate_bundle(bundle)
        self.assertEqual(active_rules(bundle),())
        self.assertEqual(bundle['sources']['sources'],[])
        self.assertTrue(all(not d['rules'] for d in bundle['rule_files']))

    def test_required_fields_are_all_mandatory(self):
        for field in self.rule:
            with self.subTest(field=field):
                bundle=deepcopy(self.bundle)
                next(d for d in bundle['rule_files'] if d['scope']=='kuha')['rules'][0].pop(field)
                with self.assertRaises(KnowledgeValidationError): validate_bundle(bundle)

    def test_unknown_identifiers_and_fields_are_rejected(self):
        variants=[('species',['unknown_fish']),('evidence_type','my_guess'),('conflict_group','unknown'),
                  ('requires',['depth']),('when',{'water_clarity':['unknown']}),
                  ('when',{'light':['moon_magic']}),('when',{'water_depth':None}),
                  ('recommend',{'methods':['unknown_method']}),('recommend',{'lure_types':['unknown_lure']}),
                  ('recommend',{'color_groups':['magic_color']})]
        for field,value in variants:
            with self.subTest(field=field,value=value):
                original=self.rule[field];self.rule[field]=value
                with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)
                self.rule[field]=original

    def test_duplicate_id_rejected_across_files_and_versions(self):
        duplicate=deepcopy(self.rule)
        duplicate['species']=['ahven'];duplicate['version']=2
        next(d for d in self.bundle['rule_files'] if d['scope']=='ahven')['rules'].append(duplicate)
        with self.assertRaisesRegex(KnowledgeValidationError,'Duplikaatti rule id'):
            validate_bundle(self.bundle)

    def test_approved_requires_a_source_and_invalid_bundle_never_activates(self):
        self.rule['status']='approved'
        with self.assertRaises(KnowledgeValidationError): active_rules(self.bundle)
        self.rule.pop('source_ids')
        with self.assertRaises(KnowledgeValidationError): active_rules(self.bundle)

    def test_nonexistent_source_is_rejected_even_for_drafts(self):
        self.rule['source_ids']=['missing']
        with self.assertRaisesRegex(KnowledgeValidationError,'Olematon source_id'):
            validate_bundle(self.bundle)

    def test_draft_and_retired_never_active_even_with_source(self):
        self.approve()
        for status in ('draft','retired'):
            self.rule['status']=status
            self.assertEqual(active_rules(self.bundle),())

    def test_only_valid_approved_rules_returned_as_independent_copies(self):
        self.approve()
        result=active_rules(self.bundle)
        self.assertEqual(len(result),1)
        result[0]['recommend']['lure_types'].append('spoon')
        self.assertEqual(self.rule['recommend']['lure_types'],['jig'])
        self.rule['version']=0
        with self.assertRaises(KnowledgeValidationError): active_rules(self.bundle)

    def test_quantities_units_ranges_and_finite_values(self):
        for value in ({'min':2,'max':1,'unit':'m'}, {'min':-1,'max':2,'unit':'m'},
                      {'min':1,'max':2,'unit':'cm'}, {'min':True,'max':2,'unit':'m'},
                      {'min':0,'max':float('inf'),'unit':'m'}, {'min':0,'max':1},
                      {'min':'1','max':2,'unit':'m'}):
            with self.subTest(value=value):
                self.rule['when']={'bottom_depth':value}
                with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)
        self.rule['when']={'bottom_depth':{'min':0,'max':2,'unit':'m'}}
        validate_bundle(self.bundle)
        self.rule['recommend']['lure_length']={'min':1,'max':2,'unit':'m'}
        with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)
        self.rule['recommend']['lure_length']['unit']='cm'
        validate_bundle(self.bundle)

    def test_temperature_can_be_negative_percent_and_hours_are_bounded(self):
        self.rule['when']={'air_temperature':{'min':-10,'max':0,'unit':'degC'}}
        validate_bundle(self.bundle)
        for field,value in [('cloud_cover',{'min':0,'max':101,'unit':'percent'}),
                            ('local_hour',{'min':23,'max':25,'unit':'hour'}),
                            ('water_temperature',{'min':-274,'max':0,'unit':'degC'})]:
            self.rule['when']={field:value}
            with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)

    def test_unknown_values_are_null_and_never_inferred(self):
        self.rule['when']={'water_temperature':None,'water_clarity':None,'fish_holding_depth':None,
                          'bottom_depth':{'min':1,'max':2,'unit':'m'},
                          'air_temperature':{'min':1,'max':2,'unit':'degC'}}
        before=deepcopy(self.bundle)
        validate_bundle(self.bundle)
        self.assertEqual(self.bundle,before)
        self.rule['requires']=['water_temperature']
        with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)

    def test_four_depth_concepts_have_independent_keys(self):
        names=('bottom_depth','fishing_depth','fish_holding_depth','lure_running_depth')
        self.rule['when']={name:{'min':i,'max':i+1,'unit':'m'} for i,name in enumerate(names)}
        validate_bundle(self.bundle)
        self.assertEqual(len(self.rule['when']),4)
        self.assertNotIn('fish_holding_depth',self.bundle['catalog']['recommendation_fields'])

    def test_sources_require_metadata_and_valid_dates(self):
        self.approve()
        self.bundle['sources']['sources'][0]['accessed_on']='2026-02-30'
        with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)
        self.bundle['sources']['sources']=[fixture_source(),fixture_source()]
        with self.assertRaises(KnowledgeValidationError): validate_bundle(self.bundle)

    def test_loader_rejects_non_json_numbers_duplicate_keys_and_missing_file(self):
        for payload in ('{"schema_version":1,"schema_version":1}', '{"rules":NaN}'):
            with TemporaryDirectory() as directory:
                shutil.copytree(KNOWLEDGE_DIR,directory,dirs_exist_ok=True)
                (Path(directory)/'conditions.json').write_text(payload,encoding='utf-8')
                with self.assertRaises(KnowledgeValidationError): load_knowledge(directory)
        with TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeValidationError): load_knowledge(directory)

    def test_management_command_is_offline(self):
        output=StringIO()
        call_command('check_fishing_knowledge',stdout=output)
        self.assertIn('0 sääntöä, 0 aktiivista',output.getvalue())
