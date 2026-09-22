"""Public weather context, separate from private fishing locations."""
import re
import time
from contextvars import ContextVar
from . import weather, geocoding
from .assistant_dates import calendar_date
from .assistant_places import forms, normalize, is_question_word

# Closed-class words and common fishing/weather vocabulary are not place evidence.
STOP = set("""entä entäs sää säätä säästä sääennuste ennuste lämpötila tuuli tuulta sade
huomenna tänään nyt ylihuomenna lähiaikoina aamulla illalla yöllä päivällä aamun illan
kannattaa lähteä lähden mennä menen kalaan kalassa kalastaa kalastamaan kalastuksessa
jigaamaan jiggaamaan jigata jigaus jiggaus uistella uistelemaan uistelu pilkillä
olisi olisipa on olen hyvä hyvät paras parhaat parhaiten parempi rauhallinen siellä sitten
voisi voisi olla paljon vähän vielä myös vain ja tai vai mutta se sen sitä tämä tuo
minun oma omat paikka paikalla paikalle paikasta järvi järvellä järvelle järveltä
kunta kylä alue alueella alueelle täällä tuolla tähän tuohon sielläkin
hauki haukea hauelle kuha kuhaa kuhalle ahven ahventa ahvenelle kala kalat
saalis saaliit reissu reissut viehe vieheet kalapaikka kalapaikat seuraavan seuraavat
päivän päivää päivän aikana kolme kolmen tuntia tunnin aikaan aika lähdössä
suosittelet suosittelisit arvio arvioi näytä kerro vertaa onnistuneita tyhjiä
ranta rannalla rannalle rannalta vene veneellä vesillä säällä sääennustetta näyttää
saanut eniten haukia ahvenia kuhia reissujani hetki
""".split())
RESOLUTION_DEADLINE = ContextVar('public_place_deadline', default=None)


class PlaceAmbiguity(ValueError):
    pass


CASE = re.compile(r'(ssa|ssä|sta|stä|lla|llä|lta|ltä|lle|([aeiouyäö])\2n)$', re.I)


def name_candidates(value):
    """At most three hypotheses; none is a resolved place without provider evidence."""
    value = normalize(value)
    if not value or is_question_word(value) or value in STOP:
        return []
    found = CASE.search(value)
    if not found:
        return [value]
    suffix = found.group()
    stem = value[:-len(suffix)] if found.group(2) is None else value[:-2]
    preferred = stem
    alternatives = []
    for ending, base in (('ntee','nne'), ('vede','vesi'), ('järve','järvi'),
                         ('lamme','lampi'), ('nieme','niemi'), ('saare','saari'), ('koske','koski')):
        if stem.endswith(ending):
            preferred = stem[:-len(ending)] + base
            break
    else:
        if stem.endswith('ee'):
            preferred = stem[:-1]
            alternatives.append(stem)
    if preferred in STOP or is_question_word(preferred):
        return []
    return list(dict.fromkeys(v for v in (preferred, *alternatives, value)
                              if len(v) >= 3 and v not in STOP and not is_question_word(v)))[:3]


def candidate_name(value):
    candidates = name_candidates(value)
    return candidates[0].capitalize() if candidates else ''


def public_candidate(question, previous=None):
    # Keep the surface form for later verification, including uncertain stem changes.
    tokens = re.findall(r'[A-Za-zÅÄÖåäö][A-Za-zÅÄÖåäö-]*', question)
    candidates = [t for t in tokens if name_candidates(t)]
    if not candidates:
        return '', '', False
    if len(candidates) > 2 or (len(candidates) > 1 and re.search(r'\b(?:vai|tai)\b', question, re.I)):
        raise PlaceAmbiguity('Anna yksi paikannimi ja tarvittaessa sen kunta tai järvi.')
    # Lowercase names need a case ending, a weather question, or a short follow-up.
    if any(not (t[0].isupper() or CASE.search(t) or
                re.search(r'\bsää(?:tä|stä|ennuste)?\b', question, re.I) or
                (previous and len(tokens) <= 2)) for t in candidates):
        return '', '', False
    bare = len(tokens) <= 2 and all(normalize(t) in ('entä','entäs') or t in candidates for t in tokens)
    followup = bool(previous and (re.match(r'^\s*entä(?:s)?\b', question, re.I) or bare))
    return candidates[0], candidates[1] if len(candidates) == 2 else '', followup


def context(value, now):
    if not isinstance(value, dict):
        return None
    try:
        if not 0 <= now.timestamp()-value['updated'] <= 21600:
            return None
        name = value['name']
        lat, lon = float(value['latitude']), float(value['longitude'])
        if not isinstance(name, str) or not re.fullmatch(r'[\wÅÄÖåäö -]{1,100}', name) or not (59 <= lat <= 71 and 19 <= lon <= 32):
            return None
        return {'name': name, 'latitude': lat, 'longitude': lon,
                'period': value['period'] if (value['period'] in ('now','today','tomorrow','next3') or calendar_date(value['period'])) else 'tomorrow',
                'osm': bool(value.get('osm')), 'updated': value['updated']}
    except (KeyError, TypeError, ValueError):
        return None


def resolve(name, area=None):
    candidates = name_candidates(name)
    found = []
    # Validate all hypotheses before choosing; two distinct places are ambiguous.
    for candidate in candidates:
        deadline = RESOLUTION_DEADLINE.get()
        if deadline is not None and time.monotonic() >= deadline:
            return None  # No partial choice when unresolved hypotheses remain.
        if found and candidate == normalize(name) and candidate != candidates[0]:
            continue  # Re-querying the already verified inflection adds no evidence.
        try:
            result = weather.resolve_place(candidate)
            canonical = result['name'].split(' (', 1)[0]
            if (59 <= result['latitude'] <= 71 and 19 <= result['longitude'] <= 32
                    and normalize(name) in forms(canonical)
                    and (not area or weather.distance(
                        (result['latitude'], result['longitude']),
                        (area['latitude'], area['longitude'])) <= 100)):
                entry = {'name': canonical, 'latitude': result['latitude'], 'longitude': result['longitude'],
                         'osm': 'OpenStreetMap' in result.get('source', '')}
                if not any(normalize(r['name']) == normalize(canonical) and weather.distance(
                        (r['latitude'],r['longitude']), (entry['latitude'],entry['longitude'])) < 1 for r in found):
                    found.append(entry)
        except weather.WeatherError:
            continue
    if found:
        return found[0] if len(found) == 1 else None
    # Only the small candidate set goes to the fallback, never question text.
    for candidate in candidates:
        deadline = RESOLUTION_DEADLINE.get()
        if deadline is not None and time.monotonic() >= deadline:
            return None  # No partial choice when unresolved hypotheses remain.
        if found and candidate == normalize(name) and candidate != candidates[0]:
            continue
        try:
            result = geocoding.lookup(candidate, area)
        except geocoding.AmbiguousGeocoding:
            return None  # Another spelling must not override known ambiguity.
        if result and normalize(name) in forms(result['name']):
            if not any(normalize(r['name']) == normalize(result['name']) and weather.distance(
                    (r['latitude'],r['longitude']), (result['latitude'],result['longitude'])) < 1 for r in found):
                found.append(result)
    return found[0] if len(found) == 1 else None


def resolve_request(question, previous, period, now):
    token = RESOLUTION_DEADLINE.set(time.monotonic() + 20)
    try:
        return _resolve_request(question, previous, period, now)
    finally:
        RESOLUTION_DEADLINE.reset(token)


def _resolve_request(question, previous, period, now):
    name, area_name, followup = public_candidate(question, previous)
    if not name:
        return None, '', period
    area = previous if followup else None
    if area_name:
        from .place_hierarchy import pair
        result = pair(name, area_name)
    else:
        result = resolve(name, area)
    notice = ''
    if not result and followup and area:
        result = dict(area)
        notice = f'Tarkkaa paikkaa ei löytynyt varmasti. Ennuste perustuu laajempaan alueeseen: {area["name"]}.'
    if result:
        period = previous['period'] if period == 'clarify' and followup else period
        result.update(period=period, updated=now.timestamp())
    return result, notice, period
