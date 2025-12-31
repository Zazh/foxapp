from django.contrib import admin
from .models import AccessToken, Visit


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ['token_short', 'booking', 'token_type', 'is_used', 'expires_at', 'created_at']
    list_filter = ['token_type', 'is_used', 'created_at']
    search_fields = ['token', 'booking__user__email', 'guest_name']
    readonly_fields = ['token', 'created_at', 'used_at']

    def token_short(self, obj):
        return f"{obj.token[:8]}..."
    token_short.short_description = 'Token'


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ['booking', 'visitor_type', 'visitor_name', 'scanned_by', 'visited_at']
    list_filter = ['visitor_type', 'visited_at']
    search_fields = ['booking__user__email', 'visitor_name']
    readonly_fields = ['visited_at']