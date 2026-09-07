from datetime import timedelta
from django.db import DatabaseError
from django.utils import timezone
from .models import AssistantUsage
from .assistant import AssistantError


def reserve(user):
    # Optimistic compare-and-swap also works on SQLite, where row locks do not.
    # Contention fails closed, without retry loops or an external call.
    try:
        usage, _ = AssistantUsage.objects.get_or_create(user=user)
        now = timezone.now()
        if usage.busy_until and usage.busy_until > now:
            raise AssistantError('Edellinen kysymys on vielä käsittelyssä. Odota hetki.')
        updated = AssistantUsage.objects.filter(pk=usage.pk, version=usage.version).update(
            version=usage.version + 1, busy_until=now + timedelta(seconds=150))
        if not updated:
            raise AssistantError('Toinen kysymys on jo käsittelyssä. Odota hetki.')
        return usage.pk, usage.version + 1
    except DatabaseError:
        raise AssistantError('Käyttörajaa ei voitu tarkistaa. Yritä myöhemmin.') from None


def release(reservation):
    try:
        pk, version = reservation
        AssistantUsage.objects.filter(pk=pk, version=version).update(busy_until=None)
    except DatabaseError:
        pass  # The lease expires; never retry a paid request.


def record_dispatch(reservation):
    """Charge once at HTTP dispatch, after local preparation and key validation."""
    try:
        pk, version = reservation
        now = timezone.now()
        usage = AssistantUsage.objects.filter(pk=pk, version=version, busy_until__gt=now).first()
        if usage is None:
            raise AssistantError('Pyynnön varaus vanheni. Lähetä kysymys uudelleen.')
        recent = [stamp for stamp in usage.attempts if stamp > (now - timedelta(hours=1)).timestamp()]
        if len(recent) >= 10:
            raise AssistantError('Tuntiraja täyttyi: enintään 10 OpenAI-kutsua tunnissa. Yritä myöhemmin uudelleen.')
        updated = AssistantUsage.objects.filter(pk=pk, version=version, attempts=usage.attempts).update(
            attempts=recent + [now.timestamp()])
        if not updated:
            raise AssistantError('Käyttörajaa ei voitu varmistaa. Yritä myöhemmin.')
    except DatabaseError:
        raise AssistantError('Käyttörajaa ei voitu tarkistaa. Yritä myöhemmin.') from None
