from django.contrib.auth.decorators import login_required
from .assistant_limits import reserve, release, record_dispatch
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .forms import AssistantForm
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
            result = advise(request.user, form.cleaned_data['question'], form.cleaned_data['place'], before_send=lambda: record_dispatch(reservation))
        except AssistantError as exc:
            form.add_error(None, str(exc))
        finally:
            if reservation is not None:
                release(reservation)
    return render(request, 'fishinglog/assistant.html', {'form': form, 'result': result, 'api_key_configured': api_key_configured()})
