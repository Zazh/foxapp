from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class Booking(models.Model):
    """Бронирование"""

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending payment')
        PAID = 'paid', _('Paid')
        ACTIVE = 'active', _('Active')
        EXPIRED = 'expired', _('Expired')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('User')
    )
    tariff = models.ForeignKey(
        'services.Tariff',
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('Tariff')
    )
    period = models.ForeignKey(
        'services.TariffPeriod',
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('Period')
    )
    storage_unit = models.ForeignKey(
        'services.StorageUnit',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='bookings',
        verbose_name=_('Storage unit'),
        help_text=_('Primary storage unit (for backward compatibility)')
    )
    storage_units = models.ManyToManyField(
        'services.StorageUnit',
        through='BookingUnit',
        related_name='bookings_multi',
        blank=True,
        verbose_name=_('Storage units'),
    )

    # Количество машин/юнитов
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Quantity'),
        help_text=_('Number of storage units booked')
    )

    # Даты
    start_date = models.DateField(verbose_name=_('Start date'))
    end_date = models.DateField(verbose_name=_('End date'))

    # Статус
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_('Status')
    )

    parent_booking = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='extensions',
        verbose_name=_('Parent booking')
    )

    # Цены (фиксируем на момент покупки)
    unit_price_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Unit price (AED)'),
        help_text=_('Per-unit price at time of booking')
    )
    price_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Period price (AED)'),
        help_text=_('Total storage cost: unit_price * quantity')
    )
    addons_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_('Addons price (AED)')
    )
    deposit_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Deposit (AED)')
    )
    total_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Total (AED)')
    )

    # Stripe
    stripe_session_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Stripe session ID')
    )
    stripe_payment_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Stripe payment ID')
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        verbose_name=_('Payment expires at'),
        help_text=_('Booking cancelled if not paid before this time')
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Paid at')
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')

    def __str__(self):
        return f"#{self.pk} — {self.user.email} — {self.tariff.name}"

    def save(self, *args, **kwargs):
        # Рассчитать end_date при создании
        if not self.end_date and self.start_date and self.period:
            self.end_date = self.period.calculate_end_date(self.start_date)

        # Установить expires_at при создании
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=30)

        # Рассчитать total
        if not self.total_aed:
            self.total_aed = self.price_aed + self.addons_aed + self.deposit_aed

        super().save(*args, **kwargs)

    @property
    def actual_status(self):
        """Проверяет и обновляет статус при обращении"""
        now = timezone.now()
        today = now.date()

        if self.status == self.Status.PENDING and self.expires_at < now:
            self.status = self.Status.CANCELLED
            self.save(update_fields=['status', 'updated_at'])

        elif self.status == self.Status.PAID and self.start_date <= today:
            self.status = self.Status.ACTIVE
            self.save(update_fields=['status', 'updated_at'])

        elif self.status == self.Status.ACTIVE and self.end_date < today:
            self.status = self.Status.COMPLETED
            # Release all storage units
            for bu in self.booking_units.select_related('storage_unit').all():
                bu.storage_unit.is_available = True
                bu.storage_unit.save(update_fields=['is_available'])
            if self.storage_unit:
                self.storage_unit.is_available = True
                self.storage_unit.save(update_fields=['is_available'])
            self.save(update_fields=['status', 'updated_at'])

        return self.status

    @property
    def days_remaining(self):
        """Дней до окончания"""
        from django.utils import timezone
        today = timezone.now().date()
        if self.end_date >= today:
            return (self.end_date - today).days
        return 0

    def assign_storage_unit(self):
        """Назначить свободное место (legacy, для одного юнита)."""
        return self.assign_storage_units()

    def assign_storage_units(self):
        """Назначить свободные места по количеству."""
        from services.models import StorageUnit

        units = list(
            StorageUnit.objects.filter(
                section__service=self.tariff.service,
                section__location=self.tariff.location,
                section__is_active=True,
                is_active=True,
                is_available=True
            ).order_by('section__sort_order', 'unit_number')[:self.quantity]
        )

        if len(units) < self.quantity:
            return False

        for unit in units:
            unit.is_available = False
            unit.save(update_fields=['is_available'])
            BookingUnit.objects.create(booking=self, storage_unit=unit)

        # Primary unit for backward compatibility
        self.storage_unit = units[0]
        self.save(update_fields=['storage_unit', 'updated_at'])
        return True

    @property
    def is_expired(self):
        """Проверяет, истёк ли срок оплаты pending бронирования"""
        return self.status == self.Status.PENDING and self.expires_at < timezone.now()

    def mark_as_paid(self, payment_id=''):
        """Отметить бронирование как оплаченное"""
        if self.is_expired:
            self.cancel()
            return False

        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.stripe_payment_id = payment_id

        if self.parent_booking:
            self.parent_booking.end_date = self.end_date
            self.parent_booking.save(update_fields=['end_date'])
        else:
            self.assign_storage_units()

        self.save()

        # Отправить уведомление
        try:
            from notifications.services import notify_booking_paid
            notify_booking_paid(self)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Notification error: {e}")

        return True

    def cancel(self):
        """Отменить бронь — освободить все юниты"""
        # Release all units via BookingUnit
        for bu in self.booking_units.select_related('storage_unit').all():
            bu.storage_unit.is_available = True
            bu.storage_unit.save(update_fields=['is_available'])
        # Also release primary unit (backward compat for old bookings)
        if self.storage_unit:
            self.storage_unit.is_available = True
            self.storage_unit.save(update_fields=['is_available'])

        self.status = self.Status.CANCELLED
        self.save(update_fields=['status', 'updated_at'])


class BookingUnit(models.Model):
    """Through model: Booking <-> StorageUnit (one per car)"""

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='booking_units',
        verbose_name=_('Booking')
    )
    storage_unit = models.ForeignKey(
        'services.StorageUnit',
        on_delete=models.PROTECT,
        related_name='booking_unit_entries',
        verbose_name=_('Storage unit')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Booking unit')
        verbose_name_plural = _('Booking units')
        unique_together = ['booking', 'storage_unit']

    def __str__(self):
        return f"{self.booking} — {self.storage_unit}"


class BookingAddon(models.Model):
    """Выбранные доп. услуги"""

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='booking_addons',
        verbose_name=_('Booking')
    )
    addon = models.ForeignKey(
        'services.AddonService',
        on_delete=models.PROTECT,
        related_name='booking_addons',
        verbose_name=_('Addon service')
    )
    price_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Price (AED)')
    )

    class Meta:
        verbose_name = _('Booking addon')
        verbose_name_plural = _('Booking addons')

    def __str__(self):
        return f"{self.booking} — {self.addon.name}"
