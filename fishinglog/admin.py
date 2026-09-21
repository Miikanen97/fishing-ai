from django.contrib import admin
from .forms import CatchForm
from .models import Trip, Catch, FishingProfile, AssistantUsage


class OwnerAdmin(admin.ModelAdmin):
    # Cross-user management is reserved to administrators, not ordinary staff.
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission


@admin.register(Trip)
class TripAdmin(OwnerAdmin):
    list_display = ('date', 'lake', 'owner', 'fishing_method', 'no_catch')
    list_filter = ('date', 'no_catch')
    search_fields = ('lake', 'owner__username')
    list_select_related = ('owner',)


class AdminCatchForm(CatchForm):
    class Meta(CatchForm.Meta):
        fields = ['trip', *CatchForm.Meta.fields]


@admin.register(Catch)
class CatchAdmin(OwnerAdmin):
    form = AdminCatchForm
    list_display = ('species', 'trip', 'owner', 'length', 'weight')
    list_select_related = ('trip__owner',)
    search_fields = ('species', 'trip__owner__username', 'trip__lake')

    @admin.display(description='Omistaja', ordering='trip__owner__username')
    def owner(self, obj):
        return obj.trip.owner


@admin.register(FishingProfile)
class FishingProfileAdmin(OwnerAdmin):
    list_display = ('user', 'default_weather_place', 'latitude', 'longitude')
    search_fields = ('user__username', 'default_weather_place')
    list_select_related = ('user',)


@admin.register(AssistantUsage)
class AssistantUsageAdmin(OwnerAdmin):
    list_display = ('user', 'busy_until')
    readonly_fields = ('user', 'attempts', 'version', 'busy_until')
    list_select_related = ('user',)

    def has_add_permission(self, request):
        return False
