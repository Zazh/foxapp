from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationTemplate(models.Model):
    """Шаблоны уведомлений"""

    class NotificationType(models.TextChoices):
        # Bookings
        BOOKING_PAID = 'booking_paid', _('Booking Paid')
        BOOKING_EXPIRING = 'booking_expiring', _('Booking Expiring Soon')
        BOOKING_EXPIRED = 'booking_expired', _('Booking Expired')
        BOOKING_EXTENDED = 'booking_extended', _('Booking Extended')

        # Visits
        VISIT_LOGGED = 'visit_logged', _('Visit Logged')
        GUEST_VISIT = 'guest_visit', _('Guest Visit')

        # Account
        WELCOME = 'welcome', _('Welcome')
        PASSWORD_CHANGED = 'password_changed', _('Password Changed')

        # Feedback
        FEEDBACK_RECEIVED = 'feedback_received', _('Feedback Received')

    class Channel(models.TextChoices):
        EMAIL = 'email', _('Email')
        TELEGRAM = 'telegram', _('Telegram')

    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        verbose_name=_('Type')
    )
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.EMAIL,
        verbose_name=_('Channel')
    )

    # Email
    email_subject = models.CharField(max_length=255, blank=True, verbose_name=_('Email Subject'))
    email_body = models.TextField(blank=True, verbose_name=_('Email Body'))

    # Telegram
    telegram_message = models.TextField(blank=True, verbose_name=_('Telegram Message'))

    is_active = models.BooleanField(default=True, verbose_name=_('Active'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Notification Template')
        verbose_name_plural = _('Notification Templates')

    def __str__(self):
        return f"{self.get_notification_type_display()} ({self.get_channel_display()})"


class NotificationLog(models.Model):
    """Лог отправленных уведомлений"""

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SENT = 'sent', _('Sent')
        FAILED = 'failed', _('Failed')

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='notification_logs',
        verbose_name=_('User')
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationTemplate.NotificationType.choices,
        verbose_name=_('Type')
    )
    channel = models.CharField(
        max_length=20,
        choices=NotificationTemplate.Channel.choices,
        verbose_name=_('Channel')
    )

    recipient = models.CharField(max_length=255, verbose_name=_('Recipient'))
    subject = models.CharField(max_length=255, blank=True, verbose_name=_('Subject'))
    body = models.TextField(verbose_name=_('Body'))

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_('Status')
    )
    error_message = models.TextField(blank=True, verbose_name=_('Error'))

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Notification Log')
        verbose_name_plural = _('Notification Logs')

    def __str__(self):
        return f"{self.notification_type} → {self.recipient} ({self.status})"