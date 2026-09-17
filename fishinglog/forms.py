from django import forms
from datetime import datetime
from .models import Catch, Trip, FishingSpot


class WeatherLookupForm(forms.Form):
    date = forms.DateField()
    time = forms.TimeField()
    place = forms.CharField(max_length=200, required=False)
    latitude = forms.DecimalField(required=False, min_value=-90, max_value=90, max_digits=8, decimal_places=5)
    longitude = forms.DecimalField(required=False, min_value=-180, max_value=180, max_digits=8, decimal_places=5)

    def clean(self):
        data = super().clean()
        lat, lon = data.get('latitude'), data.get('longitude')
        if (lat is None) != (lon is None):
            raise forms.ValidationError('Anna molemmat koordinaatit.')
        if lat is None and not data.get('place'):
            raise forms.ValidationError('Anna paikka tai koordinaatit.')
        if 'date' in data and 'time' in data:
            # Django rejects nonexistent/ambiguous Helsinki DST wall times.
            data['target'] = forms.DateTimeField().clean(datetime.combine(data['date'], data['time']))
        return data


class LogForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'
            if isinstance(field, forms.DecimalField):
                field.widget.attrs['step'] = '0.00001' if name in ('latitude', 'longitude') else '0.1'
            if name in ('depth', 'boat_speed', 'length', 'weight'):
                field.widget.attrs['min'] = '0'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 4


class SpotSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if hasattr(value, 'instance'):
            spot = value.instance
            option['attrs'].update({'data-latitude': str(spot.latitude) if spot.latitude is not None else '',
                                    'data-longitude': str(spot.longitude) if spot.longitude is not None else ''})
        return option


class TripForm(LogForm):
    save_spot = forms.BooleanField(required=False, label='Tallenna tämä paikka myös omiin kalapaikkoihin', help_text='Valitse Muu paikka ja anna nimi. Karttasijainnin voit lisätä myös myöhemmin.')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fishing_spot'].queryset = FishingSpot.objects.filter(user=user) if user and user.is_authenticated else FishingSpot.objects.none()
        self.fields['fishing_spot'].label = 'Tallennettu kalapaikka'
        self.fields['fishing_spot'].empty_label = 'Muu paikka'
        self.fields['fishing_spot'].widget = SpotSelect(choices=self.fields['fishing_spot'].choices)
        self.fields['fishing_spot'].label = 'Kalastuspaikka'
        self.fields['location'].label = 'Paikan nimi'
        self.fields['fishing_spot'].widget.attrs['class'] = 'form-select'
        self.fields['location'].required = False
        self.fields['location'].help_text = 'Muu paikka: kirjoita paikan nimi. Tallennetun kalapaikan nimi tallennetaan reissulle valinnan perusteella.'

    def clean(self):
        data = super().clean()
        spot = data.get('fishing_spot')
        if spot:
            data['location'] = spot.name
            data['latitude'], data['longitude'] = spot.latitude, spot.longitude
        elif not data.get('location'):
            self.add_error('location', 'Anna kalastuspaikan nimi tai valitse tallennettu kalapaikka.')
        if (data.get('latitude') is None) != (data.get('longitude') is None):
            raise forms.ValidationError('Anna molemmat kalastuspaikan koordinaatit tai jätä molemmat tyhjiksi.')
        return data

    def clean_no_catch(self):
        value = self.cleaned_data['no_catch']
        if value and self.instance.pk and self.instance.catches.exists():
            raise forms.ValidationError('Reissulla on jo saaliita. Poista ne ensin, jos haluat merkitä reissun saaliittomaksi.')
        return value

    class Meta:
        model = Trip
        fields = ['date', 'lake', 'fishing_spot', 'location', 'save_spot', 'start_time', 'end_time', 'weather_place', 'latitude', 'longitude', 'weather', 'air_temperature', 'wind_speed', 'wind_gust', 'wind_direction', 'air_pressure', 'cloud_cover', 'precipitation', 'weather_source', 'weather_latitude', 'weather_longitude', 'water_temperature', 'fishing_method', 'depth', 'boat_speed', 'notes', 'no_catch']
        widgets = {
            'weather_source': forms.HiddenInput(),
            'weather_latitude': forms.HiddenInput(),
            'weather_longitude': forms.HiddenInput(),
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'start_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'end_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }
        help_texts = {
            'no_catch': 'Merkitse saaliiton reissu. Voit lisätä saaliita myöhemmin, jolloin merkintä poistuu automaattisesti.',
            'latitude': 'Tarkka kalastuspaikka. Valitse piste kartalta tai anna koordinaatit käsin.',
            'longitude': 'Tarkka kalastuspaikka. Säähaun paikannimi ja havaintoasema säilyvät erillisinä.',
            'weather_place': 'Valinnainen tarkennus säähakuun, esim. Savonlinna tai 61.87, 28.88. Muuten käytetään kalastuspaikkaa. Käytä tunnistettavaa paikannimeä, tarvittaessa muodossa paikka, kunta.',
            'wind_direction': 'Suunta, josta tuulee: 0° pohjoinen, 90° itä, 180° etelä, 270° länsi.',
            'precipitation': 'Haetun ajankohdan tuntisademäärä, ei koko reissun sademäärä.',
            'end_time': 'Jos lopetusaika on ennen aloitusaikaa, reissu päättyy seuraavana päivänä.',
            'fishing_method': 'Esimerkiksi jiggaus, uistelu tai heittokalastus.',
        }


class CatchForm(LogForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('length', 'weight', 'depth'):
            field = self.fields[name]
            field.localize = True
            field.widget = forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'decimal'})
            field.widget.is_localized = True

    class Meta:
        model = Catch
        fields = ['species', 'length', 'weight', 'lure_name', 'lure_color', 'time', 'depth', 'notes']
        widgets = {'time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'})}
        help_texts = {'length': 'Metreinä, esimerkiksi 0,45. Myös desimaalipiste käy.',
                      'weight': 'Kiloina, esimerkiksi 1,25. Myös desimaalipiste käy.'}


CatchFormSet = forms.formset_factory(CatchForm, extra=0, min_num=1, validate_min=True,
                                     max_num=1000, validate_max=True, absolute_max=1000)


class CatchOutcomeForm(forms.Form):
    no_catch = forms.BooleanField(label='Ei saalista', required=False,
                                 widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))



from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


class AuthStyleMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class LoginForm(AuthStyleMixin, AuthenticationForm):
    pass


class RegistrationForm(AuthStyleMixin, UserCreationForm):
    email = forms.EmailField(label='Sähköposti', required=False)

    class Meta(UserCreationForm.Meta):
        fields = ('username', 'email')


class AssistantForm(forms.Form):
    question = forms.CharField(label='Kysymys', max_length=1000, widget=forms.Textarea(attrs={
        'class': 'form-control', 'rows': 3, 'placeholder': 'Kannattaako tänään lähteä Kyyvedelle jiggaamaan?'}))
    place = forms.CharField(label='Paikka (valinnainen)', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Esimerkiksi Kyyvesi'}),
        help_text='Kysymyksessä annettu paikka on ensisijainen. Muuten käytetään tätä paikkaa tai viimeisintä sopivaa omaa reissua.')
