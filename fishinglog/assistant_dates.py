"""Deterministic Finnish weekday dates; independent of forecast availability."""
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone

FINLAND = ZoneInfo('Europe/Helsinki')
WEEKDAYS = ('maanantai','tiistai','keskiviikko','torstai','perjantai','lauantai','sunnuntai')
FORMS = {form: index for index, name in enumerate(WEEKDAYS)
         for form in (name, name+'na')}
PATTERN = re.compile(r'\b(?:(ensi|tulevana|tänä)\s+)?('+'|'.join(sorted(FORMS,key=len,reverse=True))+r')\b', re.I)


def calendar_date(period):
    try:
        return date.fromisoformat(period) if re.fullmatch(r'\d{4}-\d{2}-\d{2}',period) else None
    except (ValueError, TypeError):
        return None


def weekday_request(question, now=None):
    now = (now or timezone.now()).astimezone(FINLAND)
    matches = list(PATTERN.finditer(question))
    if not matches:
        return None, question
    dates = set()
    for match in matches:
        modifier, word = (part.casefold() if part else '' for part in match.groups())
        weekday = FORMS[word]
        if modifier in ('ensi', 'tänä'):
            target = now.date() - timedelta(days=now.weekday()) + timedelta(days=(7 if modifier == 'ensi' else 0)+weekday)
        else:
            target = now.date() + timedelta(days=(weekday-now.weekday()) % 7)
            # After the last remaining forecast slot, an unqualified weekday means next week.
            if target == now.date() and now.hour >= 23 and modifier != 'tänä':
                target += timedelta(days=7)
        dates.add(target)
    if len(dates) != 1:
        raise ValueError('Kysymyksessä on useita päiviä. Valitse yksi viikonpäivä.')
    return dates.pop(), PATTERN.sub(' ', question)


def availability_message(period, now=None):
    target=calendar_date(period)
    if target and target < (now or timezone.now()).astimezone(FINLAND).date():
        return f'Päivämäärä tunnistettiin: {target:%d.%m.%Y}. Päivä on jo mennyt, eikä sille haeta tulevan ajan sääennustetta.'
    return (f'Päivämäärä tunnistettiin: {target:%d.%m.%Y}. Sääennustetta ei ole vielä saatavilla kyseiselle päivälle. '
            'Lähtöarviota ei voida vahvistaa.' if target else '')
