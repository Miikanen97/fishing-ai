from django import forms
from django.db.models import Count
from .models import Catch


class TripFilterForm(forms.Form):
    q = forms.CharField(label='Paikan nimi', required=False, max_length=200)
    species = forms.CharField(label='Kalalaji', required=False, max_length=100)
    outcome = forms.ChoiceField(label='Saalistila', required=False, choices=[('', 'Kaikki'), ('caught','Saalista'), ('empty','Saaliiton'), ('unknown','Ei saalistietoa')])
    start = forms.DateField(label='Alkaen', required=False, widget=forms.DateInput(attrs={'type':'date'}))
    end = forms.DateField(label='Asti', required=False, widget=forms.DateInput(attrs={'type':'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select' if isinstance(field, forms.ChoiceField) else 'form-control'

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Alkupäivä ei voi olla loppupäivän jälkeen.')
        return data


def add_species_summaries(trips, user):
    trips = list(trips)
    grouped = {}
    for row in Catch.objects.filter(trip__in=trips, trip__owner=user).values('trip_id','species').annotate(n=Count('pk')).order_by('-n','species'):
        grouped.setdefault(row['trip_id'], []).append(f"{row['species']} ×{row['n']}")
    for trip in trips:
        names = grouped.get(trip.pk, [])
        trip.species_summary = ' · '.join(names[:4]) + (' · …' if len(names)>4 else '')
    return trips
