from datetime import date
from django.utils import timezone
from .models import Catch


def monthly_top(user):
    today = timezone.localdate()
    start = today.replace(day=1)
    end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    # Explicit DTO: no Trip/FishingSpot object, place, notes or GPS in card context.
    rows = Catch.objects.filter(trip__owner=user, trip__date__gte=start, trip__date__lt=end,
                                weight__isnull=False).order_by('-weight', 'pk')[:3]
    return [{'pk': c.pk, 'species': c.species, 'weight': c.weight, 'length': c.length,
             'date': c.trip.date, 'photo': bool(c.photo)} for c in rows.select_related('trip')]
