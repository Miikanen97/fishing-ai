from django.conf import settings
from .models import FishingSpot
from django.contrib.auth.decorators import login_required
from .assistant_limits import reserve, release, record_dispatch
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .forms import AssistantForm
from .assistant_presentation import answer_summary
from .assistant import advise, AssistantError, api_key_configured


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def assistant(request):
    form = AssistantForm(request.POST if request.method == 'POST' else None)
    result = None
    if request.method == 'POST' and form.is_valid():
        reservation = None
        try:
            reservation = reserve(request.user)
            result = advise(request.user, form.cleaned_data['question'], form.cleaned_data['place'], before_send=lambda: record_dispatch(reservation), public_context=request.session.get('public_weather_context', {}), include_notes=form.cleaned_data['include_notes'])
            if result and result.get('public_context'):
                request.session['public_weather_context'] = result['public_context']
            else:
                request.session.pop('public_weather_context', None)
        except AssistantError as exc:
            message = str(exc)
            if 'OPENAI_API_KEY' in message:
                message = 'Tekoälyavustaja ei ole tällä hetkellä käytettävissä.'
            form.add_error(None, message)
        finally:
            if reservation is not None:
                release(reservation)
    return render(request, 'fishinglog/assistant.html', {'development': settings.DEBUG, 'saved_spots': FishingSpot.objects.filter(user=request.user).only('id', 'name'), 'form': form, 'result': result, 'summary': answer_summary(result), 'api_key_configured': api_key_configured()})
