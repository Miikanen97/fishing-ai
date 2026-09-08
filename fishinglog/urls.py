from django.urls import path
from . import views
from .profile_views import settings_view
from .assistant_views import assistant

app_name = 'fishinglog'
urlpatterns = [
    path('asetukset/', settings_view, name='settings'),
    path('avustaja/', assistant, name='assistant'),
    path('saa/hae/', views.weather_lookup, name='weather_lookup'),
    path('', views.home, name='home'),
    path('reissut/', views.trip_list, name='trip_list'),
    path('reissut/uusi/', views.trip_form, name='trip_create'),
    path('reissut/<int:pk>/', views.trip_detail, name='trip_detail'),
    path('reissut/<int:pk>/muokkaa/', views.trip_form, name='trip_update'),
    path('reissut/<int:pk>/poista/', views.trip_delete, name='trip_delete'),
    path('reissut/<int:trip_pk>/saaliit/uusi/', views.catch_form, name='catch_create'),
    path('reissut/<int:trip_pk>/saaliit/<int:pk>/muokkaa/', views.catch_form, name='catch_update'),
    path('reissut/<int:trip_pk>/saaliit/<int:pk>/poista/', views.catch_delete, name='catch_delete'),
]

