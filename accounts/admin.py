from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'id_card', 'is_staff', 'is_verified', 'auth_provider')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_verified', 'auth_provider')
    search_fields = ('email', 'first_name', 'last_name', 'phone', 'id_card')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone', 'id_card', 'language')}),
        (_('Auth provider'), {'fields': ('auth_provider', 'provider_id')}),
        (_('Telegram'), {'fields': ('telegram_id', 'telegram_username')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )