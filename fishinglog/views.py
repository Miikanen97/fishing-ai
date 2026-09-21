from .home_weather import home_weather
from .records import monthly_top
from django.contrib.auth.decorators import login_required

from .forms import RegistrationForm

from django.contrib import messages

from django.core.paginator import Paginator

from django.db.models import Count, Q
from .trip_history import TripFilterForm, add_species_summaries
from .trip_presentation import measurement

from django.shortcuts import get_object_or_404, redirect, render

from django.views.decorators.http import require_http_methods

from .forms import CatchForm, CatchFormSet, CatchOutcomeForm, TripForm

from django.db import transaction

from .models import Catch, Trip, FishingSpot

from django.http import JsonResponse

from .forms import WeatherLookupForm

from .weather import WeatherError, fetch_weather





@require_http_methods(['POST'])

@login_required

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

    if not request.user.is_authenticated:

        return render(request, 'fishinglog/welcome.html')

    trips = Trip.objects.filter(owner=request.user).annotate(catch_count=Count('catches')).order_by('-date', '-start_time', '-pk')

    return render(request, 'fishinglog/home.html', {'trips': add_species_summaries(trips[:5], request.user), 'monthly_top': monthly_top(request.user), 'trip_count': trips.count(), 'catch_count': Catch.objects.filter(trip__owner=request.user).count(), **home_weather(request.user)})





@login_required

def trip_list(request):

    trips = Trip.objects.filter(owner=request.user).annotate(catch_count=Count('catches'))
    filters = TripFilterForm(request.GET)
    if filters.is_valid():
        data = filters.cleaned_data
        if data.get('q'):
            trips = trips.filter(Q(lake__icontains=data['q']) | Q(location__icontains=data['q']) | Q(fishing_spot__name__icontains=data['q'], fishing_spot__user=request.user))
        if data.get('species'):
            ids = Catch.objects.filter(trip__owner=request.user, species__iexact=data['species']).values('trip_id')
            trips = trips.filter(pk__in=ids)
        if data.get('outcome') == 'caught':
            trips = trips.filter(catch_count__gt=0)
        elif data.get('outcome') == 'empty':
            trips = trips.filter(catch_count=0, no_catch=True)
        elif data.get('outcome') == 'unknown':
            trips = trips.filter(catch_count=0, no_catch=False)
        if data.get('start'):
            trips = trips.filter(date__gte=data['start'])
        if data.get('end'):
            trips = trips.filter(date__lte=data['end'])
    else:
        trips = trips.none()
    page = Paginator(trips.order_by('-date', '-start_time', '-pk'), 12).get_page(request.GET.get('page'))
    page.object_list = add_species_summaries(page.object_list, request.user)
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'fishinglog/trip_list.html', {'trips': page, 'page_obj': page,
        'filters':filters, 'filter_query':params.urlencode(), 'active_filters':[(field.label, field.value()) for field in filters if field.value()]})




@login_required

def trip_detail(request, pk):

    trip = get_object_or_404(Trip.objects.filter(owner=request.user).select_related('fishing_spot').prefetch_related('catches'), pk=pk)

    for catch in trip.catches.all():
        catch.display_weight = measurement(catch.weight)
        catch.display_length = measurement(catch.length)

    return render(request, 'fishinglog/trip_detail.html', {'trip': trip})





@require_http_methods(['GET', 'POST'])

@login_required

def trip_form(request, pk=None):

    trip = get_object_or_404(Trip, owner=request.user, pk=pk) if pk is not None else None

    form = TripForm(request.POST if request.method == 'POST' else None, instance=trip, user=request.user)
    if request.method == 'POST' and form.is_valid():

        trip = form.save(commit=False)

        trip.owner = request.user

        with transaction.atomic():
            if form.cleaned_data.get('save_spot') and not trip.fishing_spot_id:
                # Serialize same-user submissions, including concurrent saves.
                from django.contrib.auth import get_user_model
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                own = FishingSpot.objects.filter(user=request.user)
                name = trip.location.strip()
                candidates = list(own.filter(name__iexact=name)[:2])
                match = own.filter(latitude=trip.latitude, longitude=trip.longitude).first() if trip.latitude is not None else None
                if match is None and len(candidates) == 1:
                    match = candidates[0]
                if match is None:
                    match = FishingSpot.objects.create(user=request.user, name=name, latitude=trip.latitude, longitude=trip.longitude)
                elif match.latitude is None and trip.latitude is not None:
                    match.latitude, match.longitude = trip.latitude, trip.longitude
                    match.save(update_fields=['latitude', 'longitude'])
                trip.fishing_spot = match
                trip.location = match.name
                trip.latitude, trip.longitude = match.latitude, match.longitude
            trip.save()

        messages.success(request, 'Kalastusreissu tallennettu.')

        return redirect(trip)

    return render(request, 'fishinglog/trip_form.html', {'form': form, 'title': 'Muokkaa kalastusreissua' if trip else 'Lisää kalastusreissu', 'cancel_url': trip.get_absolute_url() if trip else '/'})





@require_http_methods(['GET', 'POST'])

@login_required

def trip_delete(request, pk):

    trip = get_object_or_404(Trip, owner=request.user, pk=pk)

    if request.method == 'POST':

        trip.delete()

        messages.success(request, 'Kalastusreissu ja sen saaliit poistettu.')

        return redirect('fishinglog:trip_list')

    return render(request, 'fishinglog/confirm_delete.html', {'object': trip, 'title': 'Poista kalastusreissu', 'cancel_url': trip.get_absolute_url(), 'warning': f'Myös kaikki reissun saaliit ({trip.catches.count()} kpl) poistetaan.'})





@require_http_methods(['GET', 'POST'])

@login_required

def catch_form(request, trip_pk, pk=None):

    if pk is None:

        return catch_create(request, trip_pk)

    trip = get_object_or_404(Trip, owner=request.user, pk=trip_pk)

    catch = get_object_or_404(Catch, pk=pk, trip=trip) if pk is not None else None

    form = CatchForm(request.POST if request.method == 'POST' else None, request.FILES or None, instance=catch)

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

@login_required

def catch_create(request, trip_pk):

    trip = get_object_or_404(Trip, owner=request.user, pk=trip_pk)

    data = request.POST if request.method == 'POST' else None

    outcome = CatchOutcomeForm(data, initial={'no_catch': trip.no_catch})

    formset = CatchFormSet(data, request.FILES or None, prefix='catches')

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

@login_required

def catch_delete(request, trip_pk, pk):

    catch = get_object_or_404(Catch.objects.select_related('trip'), pk=pk, trip_id=trip_pk, trip__owner=request.user)

    if request.method == 'POST':

        trip = catch.trip

        catch.delete()

        messages.success(request, 'Saalis poistettu.')

        return redirect(trip)

    return render(request, 'fishinglog/confirm_delete.html', {'object': catch, 'title': 'Poista saalis', 'cancel_url': catch.trip.get_absolute_url()})









@require_http_methods(['GET', 'POST'])

def register(request):

    if request.user.is_authenticated:

        return redirect('fishinglog:home')

    form = RegistrationForm(request.POST if request.method == 'POST' else None)

    if request.method == 'POST' and form.is_valid():

        form.save()

        messages.success(request, 'Tunnus luotu. Voit nyt kirjautua sisään.')

        return redirect('login')

    return render(request, 'registration/register.html', {'form': form})
