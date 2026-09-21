from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from .models import Catch


@never_cache
@login_required
@require_safe
def catch_photo(request, pk):
    catch = get_object_or_404(Catch, pk=pk, trip__owner=request.user)
    if not catch.photo:
        raise Http404
    try:
        response = FileResponse(catch.photo.open('rb'), content_type='image/jpeg', filename='saalis.jpg')
    except (OSError, ValueError):
        raise Http404 from None
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response
