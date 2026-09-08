from decimal import Decimal
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from .models import FishingProfile
from .weather import resolve_place, WeatherError


class ProfileForm(forms.ModelForm):
    class Meta:
        model = FishingProfile
        fields = ['default_weather_place']
        widgets = {'default_weather_place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Esimerkiksi Kyyvesi'})}
        help_texts = {'default_weather_place': 'Järvi tai kunta. Tyhjennä kenttä, jos haluat poistaa etusivun oletuspaikan.'}


@login_required
@require_http_methods(['GET', 'POST'])
def settings_view(request):
    profile = FishingProfile.objects.filter(user=request.user).first()
    form = ProfileForm(request.POST if request.method == 'POST' else None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        place = form.cleaned_data['default_weather_place']
        latitude = longitude = None
        if place:
            try:
                resolved = resolve_place(place)
                latitude = Decimal(str(resolved['latitude'])).quantize(Decimal('0.00001'))
                longitude = Decimal(str(resolved['longitude'])).quantize(Decimal('0.00001'))
            except WeatherError:
                messages.warning(request, 'Paikka tallennettiin, mutta koordinaatteja ei saatu. Tarkista paikannimi; säähakua yritetään etusivulla uudelleen.')
        FishingProfile.objects.update_or_create(user=request.user, defaults={
            'default_weather_place': place, 'latitude': latitude, 'longitude': longitude})
        messages.success(request, 'Omat asetukset tallennettu.')
        return redirect('fishinglog:settings')
    return render(request, 'fishinglog/settings.html', {'form': form, 'profile': profile})
