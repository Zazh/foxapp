import secrets
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class AccessToken(models.Model):
    """Токен доступа для QR кода"""

    class TokenType(models.TextChoices):
        OWNER = 'owner', _('Owner')
        GUEST = 'guest', _('Guest')

    booking = models.ForeignKey(
        'bookings.Booking',
        on_delete=models.CASCADE,
        related_name='access_tokens',
        verbose_name=_('Booking')
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_('Token')
    )
    token_type = models.CharField(
        max_length=10,
        choices=TokenType.choices,
        default=TokenType.OWNER,
        verbose_name=_('Token type')
    )

    # Для гостевого доступа
    guest_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Guest name')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name=_('Expires at'))
    is_used = models.BooleanField(default=False, verbose_name=_('Is used'))
    used_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Used at'))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Access token')
        verbose_name_plural = _('Access tokens')

    def __str__(self):
        return f"{self.token_type} — {self.booking.storage_unit}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            if self.token_type == self.TokenType.OWNER:
                self.expires_at = timezone.now() + timedelta(minutes=15)
            else:  # GUEST
                self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Проверка валидности токена"""
        if self.is_used and self.token_type == self.TokenType.GUEST:
            return False
        return timezone.now() < self.expires_at

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_as_used(self):
        """Отметить как использованный (для гостевых)"""
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_at'])


class Visit(models.Model):
    """Запись посещения"""

    class VisitorType(models.TextChoices):
        OWNER = 'owner', _('Owner')
        GUEST = 'guest', _('Guest')

    booking = models.ForeignKey(
        'bookings.Booking',
        on_delete=models.CASCADE,
        related_name='visits',
        verbose_name=_('Booking')
    )
    access_token = models.ForeignKey(
        AccessToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visits',
        verbose_name=_('Access token')
    )

    visitor_type = models.CharField(
        max_length=10,
        choices=VisitorType.choices,
        default=VisitorType.OWNER,
        verbose_name=_('Visitor type')
    )
    visitor_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Visitor name'),
        help_text=_('For guest visits')
    )

    # Кто зафиксировал посещение
    scanned_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scanned_visits',
        verbose_name=_('Scanned by')
    )

    visited_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Visited at'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        ordering = ['-visited_at']
        verbose_name = _('Visit')
        verbose_name_plural = _('Visits')

    def __str__(self):
        return f"{self.booking.storage_unit} — {self.visited_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def storage_unit(self):
        return self.booking.storage_unit