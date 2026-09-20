"""Explain existing scores without estimating the model's hidden weights."""
from .assistant_time import selected_time_rows


def breakdown(answer, rows):
    result = {'factors': [], 'available': False}
    selected = selected_time_rows(answer, rows)
    if len(selected) != 1 or 'score_factors' not in selected[0]:
        return result
    row = selected[0]
    labels = {'dark': 'pimeä', 'twilight': 'hämärä', 'daylight': 'valoisa',
              'unknown': 'valoisuus tuntematon', 'night': 'yö', 'morning': 'aamu',
              'day': 'päivä', 'evening': 'ilta'}
    for label, value, detail in row['score_factors']:
        if label == 'Valoisuus / vuorokaudenaika':
            detail = f"{labels[row['light']]} / {labels[row['period']]}"
        result['factors'].append({'label': label, 'detail': detail,
            'impact': f'{value:+.2f}'.replace('.', ',') if value else '0,00',
            'direction': 'Nostaa' if value > 0 else 'Laskee' if value < 0 else 'Ei pistevaikutusta'})
    result.update(available=True, total=row['priority'], place=row['place'], target=row['target'],
                  species=row.get('requested_species', ''), support=row['supporting_trips'])
    return result
