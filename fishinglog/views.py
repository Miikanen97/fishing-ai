from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import CatchForm, CatchFormSet, CatchOutcomeForm, TripForm
from django.db import transaction
from .models import Catch, Trip
from django.http import JsonResponse
from .forms import WeatherLookupForm
from .weather import WeatherError, fetch_weather


@require_http_methods(['POST'])
def weather_lookup(request):
    form = WeatherLookupForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Tarkista päivämäärä, aloitusaika ja paikka. Kesä-/talviajan vaihtumisen epäselvää tai puuttuvaa kellonaikaa ei voi käyttää.'}, status=400)
    try:
        data = form.cleaned_data
        place = f"{data['latitude']},{data['longitude']}" if data.get('latitude') is not None else data['place']
        return JsonResponse(fetch_weather(place, data['target']))
    except WeatherError as exc:
        return JsonResponse({'error': str(exc)}, status=422)


def home(request):
    trips = Trip.objects.annotate(catch_count=Count('catches')).order_by('-date', '-start_time', '-pk')
    return render(request, 'fishinglog/home.html', {'trips': trips[:5], 'trip_count': trips.count(), 'catch_count': Catch.objects.count()})


def trip_list(request):
    page = Paginator(Trip.objects.annotate(catch_count=Count('catches')).order_by('-date', '-start_time', '-pk'), 12).get_page(request.GET.get('page'))
    return render(request, 'fishinglog/trip_list.html', {'trips': page, 'page_obj': page})


def trip_detail(request, pk):
    trip = get_object_or_404(Trip.objects.prefetch_related('catches'), pk=pk)
    return render(request, 'fishinglog/trip_detail.html', {'trip': trip})


@require_http_methods(['GET', 'POST'])
def trip_form(request, pk=None):
    trip = get_object_or_404(Trip, pk=pk) if pk is not None else None
    form = TripForm(request.POST if request.method == 'POST' else None, instance=trip)
    if request.method == 'POST' and form.is_valid():
        trip = form.save()
        messages.success(request, 'Kalastusreissu tallennettu.')
        return redirect(trip)
    return render(request, 'fishinglog/form.html', {'form': form, 'title': 'Muokkaa kalastusreissua' if trip else 'Lisää kalastusreissu', 'cancel_url': trip.get_absolute_url() if trip else '/'})


@require_http_methods(['GET', 'POST'])
def trip_delete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == 'POST':
        trip.delete()
        messages.success(request, 'Kalastusreissu ja sen saaliit poistettu.')
        return redirect('fishinglog:trip_list')
    return render(request, 'fishinglog/confirm_delete.html', {'object': trip, 'title': 'Poista kalastusreissu', 'cancel_url': trip.get_absolute_url(), 'warning': f'Myös kaikki reissun saaliit ({trip.catches.count()} kpl) poistetaan.'})


@require_http_methods(['GET', 'POST'])
def catch_form(request, trip_pk, pk=None):
    if pk is None:
        return catch_create(request, trip_pk)
    trip = get_object_or_404(Trip, pk=trip_pk)
    catch = get_object_or_404(Catch, pk=pk, trip=trip) if pk is not None else None
    form = CatchForm(request.POST if request.method == 'POST' else None, instance=catch)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            catch = form.save(commit=False)
            catch.trip = trip
            catch.save()
            Trip.objects.filter(pk=trip.pk).update(no_catch=False)
        messages.success(request, 'Saalis tallennettu.')
        return redirect(trip)
    return render(request, 'fishinglog/form.html', {'form': form, 'title': 'Muokkaa saalista' if catch else 'Lisää saalis', 'trip': trip, 'cancel_url': trip.get_absolute_url()})


@require_http_methods(['GET', 'POST'])
def catch_create(request, trip_pk):
    trip = get_object_or_404(Trip, pk=trip_pk)
    data = request.POST if request.method == 'POST' else None
    outcome = CatchOutcomeForm(data, initial={'no_catch': trip.no_catch})
    formset = CatchFormSet(data, prefix='catches')
    if request.method == 'POST' and outcome.is_valid():
        if outcome.cleaned_data['no_catch']:
            with transaction.atomic():
                locked_trip = Trip.objects.select_for_update().get(pk=trip.pk)
                if locked_trip.catches.exists():
                    outcome.add_error('no_catch', 'Reissulla on jo saaliita. Saaliittomuus ei poista aiemmin tallennettuja kaloja.')
                else:
                    locked_trip.no_catch = True
                    locked_trip.save(update_fields=['no_catch'])
                    messages.success(request, 'Reissu merkitty: Ei saalista.')
                    return redirect(trip)
        elif formset.is_valid():
            with transaction.atomic():
                locked_trip = Trip.objects.select_for_update().get(pk=trip.pk)
                count = 0
                for form in formset:
                    if form.cleaned_data:
                        catch = form.save(commit=False)
                        catch.trip = locked_trip
                        catch.save()
                        count += 1
                locked_trip.no_catch = False
                locked_trip.save(update_fields=['no_catch'])
            messages.success(request, f'{count} saalista tallennettu.')
            return redirect(trip)
    return render(request, 'fishinglog/catch_formset.html', {'trip': trip, 'formset': formset, 'outcome': outcome})


@require_http_methods(['GET', 'POST'])
def catch_delete(request, trip_pk, pk):
    catch = get_object_or_404(Catch.objects.select_related('trip'), pk=pk, trip_id=trip_pk)
    if request.method == 'POST':
        trip = catch.trip
        catch.delete()
        messages.success(request, 'Saalis poistettu.')
        return redirect(trip)
    return render(request, 'fishinglog/confirm_delete.html', {'object': catch, 'title': 'Poista saalis', 'cancel_url': catch.trip.get_absolute_url()})


