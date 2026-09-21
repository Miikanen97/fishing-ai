from collections import Counter, defaultdict
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.shortcuts import render
from django.db.models import Count, Q
from .models import Trip, Catch, FishingSpot


def bars(counter):
    largest = max(counter.values(), default=1)
    return [{'label':name, 'count':count, 'width':round(100*count/largest) if largest else 0} for name,count in counter.most_common()]


@never_cache
@login_required
def statistics(request):
    trips = Trip.objects.filter(owner=request.user)
    fish = list(Catch.objects.filter(trip__owner=request.user).select_related('trip').order_by('pk'))
    productive = {catch.trip_id for catch in fish}
    species = Counter(c.species for c in fish)
    by_species = defaultdict(list)
    periods = Counter({'Aamu 05–10':0, 'Päivä 10–16':0, 'Ilta 16–22':0, 'Yö 22–05':0})
    lures = Counter()
    for catch in fish:
        by_species[catch.species].append(catch)
        hour = catch.time.hour
        periods['Aamu 05–10' if 5 <= hour < 10 else 'Päivä 10–16' if 10 <= hour < 16 else 'Ilta 16–22' if 16 <= hour < 22 else 'Yö 22–05'] += 1
        if catch.lure_name.strip():
            lures[catch.lure_name + (' · ' + catch.lure_color if catch.lure_color else '')] += 1
    def records(items):
        heavy = [c for c in items if c.weight is not None and c.weight > 0]
        long = [c for c in items if c.length is not None and c.length > 0]
        return {'heaviest':max(heavy, key=lambda c:(c.weight, -c.pk), default=None), 'longest':max(long, key=lambda c:(c.length, -c.pk), default=None)}
    # Aggregate both counts once; foreign legacy links are excluded independently.
    spot_rows = FishingSpot.objects.filter(user=request.user).annotate(
        own_trips=Count('trips', filter=Q(trips__owner=request.user), distinct=True),
        own_catches=Count('trips__catches', filter=Q(trips__owner=request.user), distinct=True),
    ).filter(own_trips__gt=0)
    spots = [{'name': spot.name, 'trips': spot.own_trips, 'count': spot.own_catches} for spot in spot_rows]
    spots.sort(key=lambda row:row['count'], reverse=True)
    total = trips.count()
    empty = trips.filter(no_catch=True).exclude(pk__in=productive).count()
    return render(request, 'fishinglog/statistics.html', {
        'total':total, 'fish_total':len(fish), 'productive':len(productive), 'empty':empty,
        'unknown':total-len(productive)-empty, 'species':bars(species), 'periods':bars(periods), 'lures':bars(lures),
        'records':[{'name':name, **records(items)} for name,items in sorted(by_species.items())],
        'overall':records(fish), 'spots':spots})
