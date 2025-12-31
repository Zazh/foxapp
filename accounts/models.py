from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Кастомная модель пользователя с email вместо username"""

    email = models.EmailField(
        _('email address'),
        unique=True,
        error_messages={
            'unique': _('A user with that email already exists.'),
        },
    )
    first_name = models.CharField(_('first name'), max_length=150)
    middle_name = models.CharField(_('middle name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150)
    phone = models.CharField(_('phone number'), max_length=20)
    id_card = models.CharField(
        _('ID card'),
        max_length=50,
        unique=True,
        error_messages={
            'unique': _('A user with that ID card already exists.'),
        },
    )

    # SSO поля
    auth_provider = models.CharField(
        _('auth provider'),
        max_length=20,
        default='email',
        choices=[
            ('email', 'Email'),
            ('google', 'Google'),
            ('apple', 'Apple'),
        ]
    )
    provider_id = models.CharField(_('provider ID'), max_length=255, blank=True)

    # Telegram интеграция
    telegram_id = models.BigIntegerField(_('Telegram ID'), null=True, blank=True, unique=True)
    telegram_username = models.CharField(_('Telegram username'), max_length=255, blank=True)

    # Статусы
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_('Designates whether this user should be treated as active.'),
    )
    is_verified = models.BooleanField(
        _('verified'),
        default=False,
        help_text=_('Designates whether this user has verified their email.'),
    )

    # Даты
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    last_login = models.DateTimeField(_('last login'), blank=True, null=True)

    # Настройки
    language = models.CharField(
        _('preferred language'),
        max_length=5,
        default='en',
        choices=[
            ('en', 'English'),
            ('ru', 'Русский'),
            ('ar', 'العربية'),
        ]
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'phone', 'id_card']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self):
        return self.email

    def get_full_name(self):
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]


class TelegramLinkToken(models.Model):
    """Токен для привязки Telegram"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telegram_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    @classmethod
    def create_for_user(cls, user):
        import secrets
        from django.utils import timezone
        from datetime import timedelta

        # Удалить старые токены
        cls.objects.filter(user=user).delete()

        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(16),
            expires_at=timezone.now() + timedelta(minutes=30)
        )

    @property
    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and timezone.now() < self.expires_at