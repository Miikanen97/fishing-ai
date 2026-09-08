from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import reverse_lazy
from fishinglog.account_views import account, delete_account, AccountPasswordChangeForm
from django.urls import include, path
from fishinglog.views import register
from fishinglog.forms import LoginForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path('profiili/', account, name='account'),
    path('profiili/poista/', delete_account, name='delete_account'),
    path('profiili/salasana/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change.html', form_class=AccountPasswordChangeForm,
        success_url=reverse_lazy('password_change_done')), name='password_change'),
    path('profiili/salasana/valmis/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'), name='password_change_done'),
    path('kirjaudu/', auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=LoginForm), name='login'),
    path('ulos/', auth_views.LogoutView.as_view(), name='logout'),
    path('rekisteroidy/', register, name='register'),
    path('', include('fishinglog.urls')),
]
