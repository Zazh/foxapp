from django.contrib import admin
from .models import FeedbackRequest


@admin.register(FeedbackRequest)
class FeedbackRequestAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    list_editable = ['status']
    search_fields = ['name', 'phone', 'email', 'message']
    readonly_fields = ['user', 'page_url', 'ip_address', 'user_agent', 'created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'phone', 'email', 'message', 'status')
        }),
        ('Manager', {
            'fields': ('manager_notes',)
        }),
        ('Meta', {
            'fields': ('user', 'page_url', 'ip_address', 'user_agent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )