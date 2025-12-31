from django.contrib import admin
from .models import NotificationTemplate, NotificationLog


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'channel', 'is_active', 'updated_at']
    list_filter = ['notification_type', 'channel', 'is_active']
    list_editable = ['is_active']

    fieldsets = (
        (None, {
            'fields': ('notification_type', 'channel', 'is_active')
        }),
        ('Email', {
            'fields': ('email_subject', 'email_body'),
        }),
        ('Telegram', {
            'fields': ('telegram_message',),
        }),
    )


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'channel', 'recipient', 'status', 'created_at']
    list_filter = ['notification_type', 'channel', 'status', 'created_at']
    search_fields = ['user__email', 'recipient']
    readonly_fields = ['user', 'notification_type', 'channel', 'recipient', 'subject', 'body',
                       'status', 'error_message', 'created_at', 'sent_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False