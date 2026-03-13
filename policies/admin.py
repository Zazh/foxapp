from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from .models import Policy, PolicyConsent


@admin.register(Policy)
class PolicyAdmin(TabbedTranslationAdmin):
    list_display = ('title', 'slug', 'is_required', 'is_active', 'sort_order')
    list_editable = ('is_active', 'is_required', 'sort_order')
    list_filter = ('is_required', 'is_active')
    search_fields = ('title',)
    prepopulated_fields = {'slug': ('title_en',)}
    ordering = ('sort_order',)

    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'content', 'consent_label')
        }),
        (_('Settings'), {
            'fields': ('is_required', 'is_active', 'sort_order')
        }),
    )


@admin.register(PolicyConsent)
class PolicyConsentAdmin(admin.ModelAdmin):
    list_display = ('user', 'policy', 'accepted_at', 'ip_address')
    list_filter = ('policy', 'accepted_at')
    search_fields = ('user__email',)
    readonly_fields = ('user', 'policy', 'accepted_at', 'ip_address')

    def has_add_permission(self, request):
        return False
