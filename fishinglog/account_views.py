from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from .forms import AuthStyleMixin


class AccountForm(AuthStyleMixin, forms.ModelForm):
    email = forms.EmailField(label='Sähköposti', required=False)

    class Meta:
        model = get_user_model()
        fields = ['email']


class AccountPasswordChangeForm(AuthStyleMixin, PasswordChangeForm):
    pass


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label='Nykyinen salasana', strip=False,
        widget=forms.PasswordInput(attrs={'class':'form-control', 'autocomplete':'current-password'}))
    confirm = forms.BooleanField(label='Ymmärrän, että tilini ja kaikki kalastustietoni poistetaan pysyvästi.',
        widget=forms.CheckboxInput(attrs={'class':'form-check-input'}))


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def account(request):
    form = AccountForm(request.POST if request.method == 'POST' else None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Sähköpostiosoite päivitetty.')
        return redirect('account')
    return render(request, 'registration/account.html', {'form': form})


@sensitive_post_parameters('password')
@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def delete_account(request):
    form = DeleteAccountForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(form.cleaned_data['password']):
                form.add_error('password', 'Salasana on virheellinen.')
            else:
                user.delete()
                logout(request)
                messages.success(request, 'Käyttäjätili ja sen kalastustiedot on poistettu.')
                return redirect('fishinglog:home')
    return render(request, 'registration/delete_account.html', {'form': form,
        'trip_count': request.user.fishing_trips.count()})
