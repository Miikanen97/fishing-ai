from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from .models import FishingSpot, Catch
from .forms import LogForm


class SpotForm(LogForm):
    def clean(self):
        from django import forms
        data = super().clean()
        if (data.get('latitude') is None) != (data.get('longitude') is None):
            raise forms.ValidationError('Anna molemmat koordinaatit tai jätä molemmat tyhjiksi.')
        return data

    class Meta:
        model = FishingSpot
        fields = ['name', 'notes', 'latitude', 'longitude']


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def spots(request, pk=None):
    own_spots = FishingSpot.objects.filter(user=request.user)
    spot = get_object_or_404(own_spots, pk=pk) if pk is not None else None
    form = SpotForm(request.POST if request.method == 'POST' else None, instance=spot)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, 'Kalapaikka tallennettu.')
        return redirect('fishinglog:spots')
    species = {}
    for row in Catch.objects.filter(trip__owner=request.user, trip__fishing_spot__user=request.user).values('trip__fishing_spot_id', 'species').annotate(total=Count('pk')).order_by('-total', 'species'):
        species.setdefault(row['trip__fishing_spot_id'], []).append(row['species'])
    own_spots = own_spots.annotate(
        trip_count=Count('trips', filter=Q(trips__owner=request.user), distinct=True),
        catch_count=Count('trips__catches', filter=Q(trips__owner=request.user), distinct=True))
    data = [{'id': item.pk, 'name': item.name, 'trip_count': item.trip_count, 'catch_count': item.catch_count, 'species_summary': ' · '.join(species.get(item.pk, [])[:4]), 'notes': item.notes, 'latitude': str(item.latitude) if item.latitude is not None else None, 'longitude': str(item.longitude) if item.longitude is not None else None,
             'edit_url': reverse('fishinglog:spot_update', args=[item.pk]),
             'delete_url': reverse('fishinglog:spot_delete', args=[item.pk])} for item in own_spots]
    return render(request, 'fishinglog/spots.html', {'form': form, 'spot': spot, 'spots': data})


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def delete_spot(request, pk):
    spot = get_object_or_404(FishingSpot.objects.filter(user=request.user), pk=pk)
    if request.method == 'POST':
        spot.delete()
        messages.success(request, 'Kalapaikka poistettu.')
        return redirect('fishinglog:spots')
    return render(request, 'fishinglog/confirm_delete.html', {'object': spot, 'title': 'Poista kalapaikka',
        'cancel_url': reverse('fishinglog:spots')})
