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

    # Снепшоты (фиксируем на момент покупки)
    tariff_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Tariff name'),
        help_text=_('Snapshot of tariff name at time of booking')
    )
    service_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Service name'),
        help_text=_('Snapshot of service name at time of booking')
    )
    location_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Location'),
        help_text=_('Snapshot of location name at time of booking')
    )
    period_label = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Period label'),
        help_text=_('e.g. "3 months", "30 days"')
    )
    unit_codes = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_('Unit codes'),
        help_text=_('Comma-separated unit codes at time of booking')
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
    stripe_receipt_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name=_('Stripe receipt URL')
    )

    # Manager notes
    manager_notes = models.TextField(
        blank=True,
        verbose_name=_('Manager notes'),
        help_text=_('Internal notes (refunds, reassign reasons, etc.)')
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
        indexes = [
            models.Index(
                fields=['status', 'end_date'],
                name='idx_booking_status_end',
            ),
            models.Index(
                fields=['status', 'parent_booking'],
                name='idx_booking_status_parent',
            ),
        ]

    def __str__(self):
        name = self.tariff_name or (self.tariff.name if self.tariff_id else '—')
        return f"#{self.pk} — {self.user.email} — {name}"

    @property
    def is_extension(self):
        return self.parent_booking_id is not None

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

        # Снепшоты при создании
        if not self.pk:
            self._fill_snapshots()

        super().save(*args, **kwargs)

    def _fill_snapshots(self):
        """Заполнить снепшот-поля из связанных объектов."""
        if not self.tariff_name and self.tariff_id:
            self.tariff_name = self.tariff.name
        if not self.service_name and self.tariff_id:
            self.service_name = self.tariff.service.name
        if not self.location_name and self.tariff_id:
            self.location_name = self.tariff.location.name
        if not self.period_label and self.period_id:
            self.period_label = self.period.duration_display
        if not self.unit_codes and self.storage_unit_id:
            self.unit_codes = self.storage_unit.full_code

    @property
    def days_remaining(self):
        """Дней до окончания"""
        today = timezone.now().date()
        if self.end_date >= today:
            return (self.end_date - today).days
        return 0

    @property
    def days_overdue(self):
        """Дней просрочки после end_date"""
        today = timezone.now().date()
        if self.end_date < today:
            return (today - self.end_date).days
        return 0

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
        self.unit_codes = ', '.join(u.full_code for u in units)
        self.save(update_fields=['storage_unit', 'unit_codes', 'updated_at'])
        return True

    @property
    def is_expired(self):
        """Проверяет, истёк ли срок оплаты pending бронирования"""
        return self.status == self.Status.PENDING and self.expires_at < timezone.now()

    def mark_as_paid(self, payment_id='', receipt_url=''):
        """Отметить бронирование как оплаченное.

        Основное бронирование: назначает юниты, статус → paid.
        Продление: обновляет end_date родителя, статус продления → completed.
        """
        if self.is_expired:
            self.cancel()
            return False

        self.paid_at = timezone.now()
        self.stripe_payment_id = payment_id
        if receipt_url:
            self.stripe_receipt_url = receipt_url

        if self.is_extension:
            # Продление: обновить родителя, себя пометить completed
            parent = self.parent_booking
            parent.end_date = self.end_date
            parent.save(update_fields=['end_date', 'updated_at'])
            self.status = self.Status.COMPLETED
        else:
            # Новое бронирование: назначить юниты
            self.status = self.Status.PAID
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

    def activate(self):
        """Перевести в активный статус (вызывается management-командой)."""
        if self.status == self.Status.PAID and self.start_date <= timezone.now().date():
            self.status = self.Status.ACTIVE
            self.save(update_fields=['status', 'updated_at'])

    def expire(self):
        """Срок аренды истёк, но машина ещё в ячейке.

        Юниты НЕ освобождаются — менеджер должен убедиться что
        машина забрана и сделать Force Release вручную.
        """
        if self.status != self.Status.ACTIVE:
            return
        self.status = self.Status.EXPIRED
        self.save(update_fields=['status', 'updated_at'])

    def complete(self):
        """Завершить бронирование и освободить юниты.

        Вызывается менеджером через Force Release после того как
        убедился что машина/вещи забраны из ячейки.
        """
        self._release_units()
        self.status = self.Status.COMPLETED
        self.save(update_fields=['status', 'updated_at'])

    def cancel(self):
        """Отменить бронь.

        Продление НЕ трогает юниты — они принадлежат родителю.
        Основное бронирование — освобождает юниты.
        """
        if not self.is_extension:
            self._release_units()

        self.status = self.Status.CANCELLED
        self.save(update_fields=['status', 'updated_at'])

    def reassign_unit(self, old_unit, new_unit):
        """Переселить бронирование с одного юнита на другой.

        Освобождает old_unit, занимает new_unit, обновляет BookingUnit,
        storage_unit (primary) и снепшот unit_codes.
        """
        if self.status not in [self.Status.PAID, self.Status.ACTIVE, self.Status.EXPIRED]:
            raise ValueError(f'Cannot reassign unit for booking in status {self.status}')

        if not new_unit.is_available or not new_unit.is_active:
            raise ValueError(f'Unit {new_unit.full_code} is not available')

        # Освободить старый юнит
        old_unit.is_available = True
        old_unit.save(update_fields=['is_available'])

        # Занять новый юнит
        new_unit.is_available = False
        new_unit.save(update_fields=['is_available'])

        # Обновить BookingUnit
        self.booking_units.filter(storage_unit=old_unit).update(storage_unit=new_unit)

        # Обновить primary unit
        if self.storage_unit_id == old_unit.pk:
            self.storage_unit = new_unit

        # Обновить снепшот unit_codes
        current_units = [
            bu.storage_unit for bu in
            self.booking_units.select_related('storage_unit__section__location').all()
        ]
        self.unit_codes = ', '.join(u.full_code for u in current_units)
        self.save(update_fields=['storage_unit', 'unit_codes', 'updated_at'])

    def _release_units(self):
        """Освободить все юниты этого бронирования."""
        for bu in self.booking_units.select_related('storage_unit').all():
            bu.storage_unit.is_available = True
            bu.storage_unit.save(update_fields=['is_available'])
        if self.storage_unit:
            self.storage_unit.is_available = True
            self.storage_unit.save(update_fields=['is_available'])


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
