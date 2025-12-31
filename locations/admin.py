# locations/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from .models import Location


@admin.register(Location)
class LocationAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'location_type', 'street', 'building', 'phone', 'is_active', 'sort_order')
    list_filter = ('is_active', 'location_type')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'street', 'building', 'phone', 'email')

    fieldsets = (
        (None, {
            'fields': ('location_type', 'name', 'description')
        }),
        (_('Address'), {
            'fields': ('street', 'building')
        }),
        (_('Coordinates'), {
            'fields': ('latitude', 'longitude'),
            'description': _('Get coordinates from Google Maps')
        }),
        (_('Contact'), {
            'fields': ('phone', 'email', 'working_hours')
        }),
        (_('Settings'), {
            'fields': ('is_active', 'sort_order')
        }),
    )