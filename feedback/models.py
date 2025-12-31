from django.db import models
from django.utils.translation import gettext_lazy as _


class FeedbackRequest(models.Model):
    """Заявка на обратную связь"""

    class Status(models.TextChoices):
        NEW = 'new', _('New')
        IN_PROGRESS = 'in_progress', _('In Progress')
        RESOLVED = 'resolved', _('Resolved')
        CLOSED = 'closed', _('Closed')

    name = models.CharField(max_length=100, verbose_name=_('Name'))
    phone = models.CharField(max_length=20, verbose_name=_('Phone'))
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    message = models.TextField(blank=True, verbose_name=_('Message'))

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name=_('Status')
    )

    # Связь с пользователем (если авторизован)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedback_requests',
        verbose_name=_('User')
    )

    # Метаданные
    page_url = models.URLField(blank=True, verbose_name=_('Page URL'))
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name=_('IP Address'))
    user_agent = models.TextField(blank=True, verbose_name=_('User Agent'))

    # Для менеджера
    manager_notes = models.TextField(blank=True, verbose_name=_('Manager Notes'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Feedback Request')
        verbose_name_plural = _('Feedback Requests')

    def __str__(self):
        return f"{self.name} — {self.phone} ({self.get_status_display()})"