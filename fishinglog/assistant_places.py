"""Conservative Finnish place matching, without geocoding or capitalization guesses."""
import re
import unicodedata

QUESTION_WORDS = frozenset('monelta milloin missä mihin minne mistä missäpäin mihinpäin mistäpäin kannattaako koska miksi miten kuinka mitä mikä mitkä ketkä kuka kenelle keneltä kenellä kenen kumpi kumman kummalla kummalle kummalta paljonko montako moniko monenko kauanko millainen millaiset millaisella millä miltä mille minkä minkälainen onko olisiko voiko saako pitäisikö joko eikö'.split())
KNOWN_PLACES = ('Kyyvesi', 'Jyväskylä', 'Kangasniemi')


def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def is_question_word(word):
    return word in QUESTION_WORDS or any(word == base + suffix for base in QUESTION_WORDS for suffix in ('ko', 'kö', 'han', 'hän', 'kaan', 'kään'))


def forms(name):
    name = normalize(name)
    if not name or any(is_question_word(word) for word in name.split()):
        return set()
    variants = {name}
    # Generate forms from a known name; never strip an unknown word into a guess.
    stems = {name}
    for ending, stem in [('vesi', 'vede'), ('järvi', 'järve'), ('lampi', 'lamme'), ('niemi', 'nieme'), ('saari', 'saare'), ('koski', 'koske')]:
        if name.endswith(ending):
            stems = {name[:-len(ending)] + stem}
            break
    for stem in stems:
        variants.update(stem + suffix for suffix in ('ssa', 'ssä', 'sta', 'stä', 'lla', 'llä', 'lta', 'ltä', 'lle', 'n'))
        if stem[-1:] in 'aeiouyäö':
            variants.add(stem + stem[-1] + 'n')
    variants.update(name + '-' + suffix for suffix in ('paikka', 'paikalle', 'paikalla', 'paikalta'))
    return variants


def matches(question, names):
    text = normalize(question)
    found = []
    for name in names:
        spans = [match.span() for form in forms(name)
                 for match in re.finditer(r'(?<![\w-])' + re.escape(form) + r'(?![\w-])', text)]
        if spans:
            found.append((name, spans))
    # A full multiword name wins over another place embedded inside that name.
    return [name for name, spans in found if not all(
        any(start <= a and b <= end and (start, end) != (a, b)
            for other, other_spans in found if other != name for start, end in other_spans)
        for a, b in spans)]


def identify_place(question, saved_names=()):
    own = matches(question, saved_names)
    if own:
        return own[0] if len(own) == 1 else ''
    known = matches(question, KNOWN_PLACES)
    if known:
        return known[0] if len(known) == 1 else ''
    # Optional explicit user notation, not arbitrary capitalized prose.
    explicit = re.findall(r'\b(?:paikka|järvi|kunta)\s*:\s*"([^"\n]{1,200})"', question, re.I)
    if len(explicit) == 1 and forms(explicit[0]):
        return explicit[0].strip()
    return ''
