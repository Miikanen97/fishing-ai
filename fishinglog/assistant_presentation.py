"""Presentation only: no database, weather or AI calls."""
import re


def answer_summary(result):
    result = result if isinstance(result, dict) else {}
    answer = result.get('answer') or {}
    score = answer.get('score')
    valid = type(score) is int and 1 <= score <= 10
    label, color = ('Ei arvioitu', 'secondary')
    if valid:
        label, color = ('Heikko', 'danger') if score <= 3 else ('Kohtalainen', 'warning') if score <= 6 else ('Hyvä', 'success') if score <= 8 else ('Erinomainen', 'primary')
    rationale = answer.get('rationale') or ''
    sections = []
    parts = re.split(r'(Oma historia|Sääennuste|Oma arvio)\s*:', rationale)
    if len(parts) > 1 and not parts[0].strip():
        sections = [{'title': parts[i], 'text': parts[i+1].strip()} for i in range(1, len(parts), 2)]
    recommendation = (answer.get('recommendation') or '').strip()
    place = (result.get('place') or '').strip()
    spots = result.get('spot_history_summary') or []
    names = {spot['name'].strip() for spot in spots if spot.get('name')}
    if place:
        names.add(place)
    # Only an unambiguous, explicit place-only recommendation identifies a winner.
    matched = [name for name in names if name.casefold() == recommendation.rstrip('.!').casefold()]
    recommended = matched[0] if len(matched) == 1 and not result.get('warning') else None
    if not recommendation or matched:
        details = []
        if recommendation:
            details.append('Paikka: ' + matched[0])
        elif place:
            details.append('Paikka: ' + place)
        for field, title in [('best_time', 'Paras arvioitu aika'), ('species', 'Kohdekala'), ('method', 'Kalastustapa')]:
            value = answer.get(field)
            if isinstance(value, str) and value.strip():
                details.append(title + ': ' + value.strip())
        recommendation = '. '.join(part.rstrip('.') for part in details) + '.' if details else 'Suositusta ei ole saatavilla.'
    comparison = [{**spot, 'recommended': spot.get('name') == recommended} for spot in spots]
    return {'recommendation': recommendation, 'comparison': comparison, 'score': score if valid else None, 'label': label, 'color': color,
            'percent': score * 10 if valid else 0, 'sections': sections}
