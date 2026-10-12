"""Offline knowledge validation only. No recommendation engine or AI integration."""
from copy import deepcopy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError, SchemaError

KNOWLEDGE_DIR = Path(__file__).resolve().parent / 'knowledge'


class KnowledgeValidationError(ValueError):
    pass


def _reject_constant(value):
    raise KnowledgeValidationError('JSONissa ei sallita NaN- tai Infinity-arvoja.')


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise KnowledgeValidationError(f'Duplikaatti JSON-avain: {key}')
        result[key] = value
    return result


def _read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'), parse_constant=_reject_constant,
                          object_pairs_hook=_unique_keys)
    except (OSError, ValueError) as exc:
        raise KnowledgeValidationError(f'{path.name}: {exc}') from exc


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_bundle(bundle, schema=None):
    schema = schema if schema is not None else _read(KNOWLEDGE_DIR / 'schema.json')
    for value in _walk(schema):
        if isinstance(value, dict) and '$ref' in value and not value['$ref'].startswith('#/'):
            raise KnowledgeValidationError('Schema-viitteiden pitää olla paikallisia.')
    for value in _walk(bundle):
        if isinstance(value, float) and not math.isfinite(value):
            raise KnowledgeValidationError('Lukuarvon pitää olla äärellinen.')
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(bundle)
    except (ValidationError, SchemaError) as exc:
        raise KnowledgeValidationError(str(exc)) from exc
    catalog = bundle['catalog']
    groups = catalog['groups']
    required_groups = {'species','methods','lures','water_clarity','light','seasons',
                       'pressure_trends','color_groups','evidence_types','conflict_groups'}
    if not required_groups <= groups.keys() or any(not groups[k] for k in required_groups):
        raise KnowledgeValidationError('Katalogista puuttuu vaadittu tunnisteryhmä.')

    def member(value, group):
        if value not in groups[group]:
            raise KnowledgeValidationError(f'Tuntematon tunniste {group}: {value}')

    for fields in (catalog['condition_fields'], catalog['recommendation_fields']):
        for name, spec in fields.items():
            if spec['kind'] == 'category' and spec['catalog_group'] not in groups:
                raise KnowledgeValidationError(f'Tuntematon katalogiryhmä: {name}')
            if spec['kind'] == 'quantity' and spec['minimum'] is not None and spec['maximum'] is not None and spec['minimum'] > spec['maximum']:
                raise KnowledgeValidationError(f'Virheellinen katalogin lukuväli: {name}')

    def fields_valid(values, specs):
        for name, value in values.items():
            if name not in specs:
                raise KnowledgeValidationError(f'Tuntematon kenttä: {name}')
            if value is None:
                continue  # Explicitly unknown; never infer or substitute another field.
            spec = specs[name]
            if spec['kind'] == 'category':
                if not isinstance(value, list):
                    raise KnowledgeValidationError(f'{name}: odotettiin tunnistelistaa.')
                for item in value:
                    member(item, spec['catalog_group'])
            else:
                if not isinstance(value, dict) or value['unit'] != spec['unit']:
                    raise KnowledgeValidationError(f'{name}: väärä yksikkö tai arvotyyppi.')
                if value['min'] > value['max']:
                    raise KnowledgeValidationError(f'{name}: min on suurempi kuin max.')
                if ((spec['minimum'] is not None and value['min'] < spec['minimum']) or
                    (spec['maximum'] is not None and value['max'] > spec['maximum'])):
                    raise KnowledgeValidationError(f'{name}: arvo ei ole sallitulla välillä.')

    sources = {}
    for source in bundle['sources']['sources']:
        if source['id'] in sources:
            raise KnowledgeValidationError('Duplikaatti lähdetunniste.')
        member(source['evidence_type'], 'evidence_types')
        sources[source['id']] = source
    seen, scopes = set(), set()
    for document in bundle['rule_files']:
        scope = document['scope']
        if scope in scopes:
            raise KnowledgeValidationError(f'Duplikaatti sääntötiedoston scope: {scope}')
        scopes.add(scope)
        if scope != 'conditions':
            member(scope, 'species')
        for rule in document['rules']:
            if rule['id'] in seen:
                raise KnowledgeValidationError(f'Duplikaatti rule id: {rule["id"]}')
            seen.add(rule['id'])
            for species in rule['species']:
                member(species, 'species')
            if scope != 'conditions' and rule['species'] != [scope]:
                raise KnowledgeValidationError('Lajitiedoston sääntö kuuluu väärälle lajille.')
            for group in ('evidence_type','conflict_group'):
                member(rule[group], {'evidence_type':'evidence_types','conflict_group':'conflict_groups'}[group])
            if any(source not in sources for source in rule['source_ids']):
                raise KnowledgeValidationError(f'Olematon source_id: {rule["id"]}')
            fields_valid(rule['when'], catalog['condition_fields'])
            fields_valid(rule['recommend'], catalog['recommendation_fields'])
            for field in rule['requires']:
                if field not in catalog['condition_fields']:
                    raise KnowledgeValidationError(f'Tuntematon requires-kenttä: {field}')
                if field in rule['when'] and rule['when'][field] is None:
                    raise KnowledgeValidationError('Sama kenttä ei voi olla sekä tunnettu että unknown.')
    if scopes != {'conditions', *groups['species']}:
        raise KnowledgeValidationError('Jokaiselle lajille ja yleisille ehdoille vaaditaan tiedosto.')


def load_knowledge(directory=KNOWLEDGE_DIR):
    directory = Path(directory)
    documents = [_read(directory / 'conditions.json')]
    for path in sorted((directory / 'species').glob('*.json')):
        document = _read(path)
        if document.get('scope') != path.stem:
            raise KnowledgeValidationError('Lajitiedoston nimi ja scope eivät vastaa toisiaan.')
        documents.append(document)
    bundle = {'catalog':_read(directory/'catalog.json'), 'sources':_read(directory/'sources.json'),
              'rule_files':documents}
    validate_bundle(bundle, _read(directory/'schema.json'))
    return bundle


def active_rules(bundle=None):
    """Return only approved, validated rules. Not an applicability/recommendation selector."""
    bundle = load_knowledge() if bundle is None else bundle
    validate_bundle(bundle)
    return tuple(deepcopy(rule) for document in bundle['rule_files'] for rule in document['rules']
                 if rule['status'] == 'approved')
