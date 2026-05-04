from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Booking, BookingAddon, BookingUnit


class BookingAddonInline(admin.TabularInline):
    model = BookingAddon
    extra = 0
    readonly_fields = ('addon', 'price_aed')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BookingUnitInline(admin.TabularInline):
    model = BookingUnit
    extra = 0
    readonly_fields = ('storage_unit', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'user', 'tariff', 'period', 'quantity', 'storage_unit',
        'status_badge', 'unit_price_aed', 'total_aed', 'start_date', 'end_date', 'created_at'
    )
    list_filter = ('status', 'tariff__service', 'tariff__location', 'created_at')
    search_fields = ('number', 'user__email', 'user__first_name', 'user__last_name', 'stripe_payment_id')
    ordering = ('-created_at',)
    readonly_fields = (
        'number',
        'stripe_session_id', 'stripe_payment_id', 'paid_at',
        'created_at', 'updated_at', 'expires_at', 'total_aed',
        'unit_price_aed',
        'tariff_name', 'service_name', 'location_name', 'period_label', 'unit_codes',
    )
    autocomplete_fields = ('user', 'tariff', 'period', 'storage_unit')
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('number', 'user', 'tariff', 'period', 'storage_unit', 'quantity')
        }),
        (_('Dates'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Status'), {
            'fields': ('status',)
        }),
        (_('Pricing'), {
            'fields': ('unit_price_aed', 'price_aed', 'addons_aed', 'deposit_aed', 'total_aed')
        }),
        (_('Notes'), {
            'fields': ('manager_notes',),
        }),
        (_('Snapshots'), {
            'fields': ('tariff_name', 'service_name', 'location_name', 'period_label', 'unit_codes'),
            'classes': ('collapse',),
        }),
        (_('Stripe'), {
            'fields': ('stripe_session_id', 'stripe_payment_id', 'paid_at'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [BookingUnitInline, BookingAddonInline]

    def status_badge(self, obj):
        # Используем display_status, который различает active/overdue по датам
        colors = {
            'pending': '#f59e0b',  # orange
            'paid': '#3b82f6',  # blue (paid, ещё не активирован — start_date в будущем)
            'active': '#10b981',  # green (start_date наступил, end_date в будущем)
            'overdue': '#ef4444',  # red (end_date в прошлом, юнит требует release)
            'completed': '#6b7280',  # gray
            'cancelled': '#9ca3af',  # light gray
        }
        ds = obj.display_status
        color = colors.get(ds, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:10px; font-size:11px; font-weight:bold;">{}</span>',
            color,
            obj.display_status_label
        )

    status_badge.short_description = _('Status')

    actions = ['mark_cancelled']

    @admin.action(description=_('Cancel selected bookings'))
    def mark_cancelled(self, request, queryset):
        for booking in queryset:
            if booking.status not in ['completed', 'cancelled']:
                booking.cancel()
        self.message_user(request, _('Selected bookings have been cancelled.'))


@admin.register(BookingAddon)
class BookingAddonAdmin(admin.ModelAdmin):
    list_display = ('booking', 'addon', 'price_aed')
    list_filter = ('addon',)
    search_fields = ('booking__user__email', 'addon__name')
    ordering = ('-booking__created_at',)
    autocomplete_fields = ('booking', 'addon')
