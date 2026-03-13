from django.db import models
from django.utils.translation import gettext_lazy as _


class Policy(models.Model):
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    slug = models.SlugField(max_length=255, unique=True, verbose_name=_('Slug'))
    content = models.TextField(verbose_name=_('Content'), help_text=_('HTML allowed'))
    consent_label = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name=_('Consent label'),
        help_text=_('Use {link} for auto-link to policy, e.g. "I have read and accept the {link}"')
    )
    is_required = models.BooleanField(
        default=False,
        verbose_name=_('Required for booking'),
        help_text=_('User must accept before booking')
    )
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Policy')
        verbose_name_plural = _('Policies')

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('policy_detail', kwargs={'slug': self.slug})

    def get_consent_html(self):
        link = f'<a href="{self.get_absolute_url()}" target="_blank" class="text-orange-500 underline hover:text-orange-600">{self.title}</a>'
        if self.consent_label:
            return self.consent_label.replace('{link}', link)
        return f'I have read and accept the {link}'


class PolicyConsent(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='policy_consents',
        verbose_name=_('User')
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='consents',
        verbose_name=_('Policy')
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(verbose_name=_('IP address'), null=True, blank=True)

    class Meta:
        verbose_name = _('Policy consent')
        verbose_name_plural = _('Policy consents')
        unique_together = ['user', 'policy']

    def __str__(self):
        return f"{self.user.email} — {self.policy.title}"
