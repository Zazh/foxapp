from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class Booking(models.Model):
    """Бронирование"""

    class Status(models.TextChoices):
        # Booking — это контракт оплаты. "Active" / "Expired" — производное от
        # дат, а не отдельные статусы. См. helpers active_qs() / overdue_qs()
        # и property display_status.
        PENDING = 'pending', _('Pending payment')
        PAID = 'paid', _('Paid')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    class PaymentMethod(models.TextChoices):
        LK_INVOICE = 'lk_invoice', _('Online (Stripe Checkout in cabinet)')
        CASH = 'cash', _('Cash / terminal at desk')
        STRIPE_PAYMENT_LINK = 'stripe_payment_link', _('Stripe Payment Link (manager-sent)')

    number = models.CharField(
        max_length=5,
        unique=True,
        verbose_name=_('Booking number'),
        help_text=_('Human-readable 5-digit ID shown to customers'),
    )
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

    # Способ оплаты — выбирает менеджер при создании booking из бэкофиса.
    # lk_invoice — стандартный self-service флоу через Stripe Checkout в ЛК.
    # cash и stripe_payment_link — деньги принимает менеджер вне нашей системы.
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.LK_INVOICE,
        verbose_name=_('Payment method'),
    )
    payment_amount_collected = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Amount collected'),
        help_text=_('Actual amount the manager collected (cash/payment_link). For reporting.'),
    )
    created_by_manager = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings_created_as_manager',
        verbose_name=_('Created by manager'),
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
        return f"#{self.number or self.pk} — {self.user.email} — {name}"

    @property
    def is_extension(self):
        return self.parent_booking_id is not None

    @classmethod
    def active_qs(cls, today=None):
        """Бронирования, по которым клиент сейчас обслуживается.

        PAID + start_date наступил + end_date ещё не прошёл.
        Не включает extensions (они только обновляют end_date родителя).
        """
        today = today or timezone.now().date()
        return cls.objects.filter(
            status=cls.Status.PAID,
            parent_booking__isnull=True,
            start_date__lte=today,
            end_date__gte=today,
        )

    @classmethod
    def overdue_qs(cls, today=None):
        """Бронирования, у которых истёк срок, но юнит ещё занят.

        PAID + end_date в прошлом. Менеджер должен сделать Force Release
        или продлить (extension).
        """
        today = today or timezone.now().date()
        return cls.objects.filter(
            status=cls.Status.PAID,
            parent_booking__isnull=True,
            end_date__lt=today,
        )

    @classmethod
    def occupies_unit_qs(cls):
        """PAID-брони, которые сейчас держат за собой юнит.

        Эквивалент старого `status__in=[PAID, ACTIVE, EXPIRED]` —
        пока booking не COMPLETED/CANCELLED, юнит за ним.
        """
        return cls.objects.filter(
            status=cls.Status.PAID,
            parent_booking__isnull=True,
        )

    @property
    def is_active(self):
        """Сейчас в активном использовании."""
        if self.status != self.Status.PAID:
            return False
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def is_overdue(self):
        """PAID, но end_date в прошлом — юнит держится, нужна реакция менеджера."""
        if self.status != self.Status.PAID:
            return False
        return self.end_date < timezone.now().date()

    @property
    def display_status(self):
        """Производный статус для UI: pending/paid/active/overdue/completed/cancelled."""
        if self.status != self.Status.PAID:
            return self.status
        today = timezone.now().date()
        if self.end_date < today:
            return 'overdue'
        if self.start_date > today:
            return 'paid'  # оплачено, но ещё не началось
        return 'active'

    @property
    def display_status_label(self):
        """Человекочитаемая метка для display_status."""
        labels = {
            'pending': _('Pending payment'),
            'paid': _('Paid (upcoming)'),
            'active': _('Active'),
            'overdue': _('Overdue'),
            'completed': _('Completed'),
            'cancelled': _('Cancelled'),
        }
        return labels.get(self.display_status, self.get_status_display())

    @classmethod
    def _generate_number(cls):
        """Сгенерировать следующий свободный 5-значный номер.

        Сквозная нумерация для всех Booking, включая extensions.
        Race condition защищён unique-индексом + retry в save().
        """
        from django.db.models import IntegerField
        from django.db.models.functions import Cast

        last = (
            cls.objects.exclude(number='')
            .annotate(num_int=Cast('number', IntegerField()))
            .order_by('-num_int')
            .first()
        )
        next_n = 1
        if last and last.number and last.number.isdigit():
            next_n = int(last.number) + 1
        return f"{next_n:05d}"

    def save(self, *args, **kwargs):
        from django.db import IntegrityError

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

        # Сгенерировать номер при создании. На случай гонки — несколько ретраев.
        if not self.pk and not self.number:
            for attempt in range(5):
                self.number = self._generate_number()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.number = ''
                    if attempt == 4:
                        raise

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

    @transaction.atomic
    def assign_storage_units(self):
        """Назначить свободные места по количеству.

        Использует select_for_update для предотвращения race condition
        при одновременном бронировании.
        """
        from services.models import StorageUnit

        units = list(
            StorageUnit.objects.select_for_update().filter(
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

    @transaction.atomic
    def mark_as_paid(self, payment_id='', receipt_url=''):
        """Отметить бронирование как оплаченное.

        Основное бронирование: назначает юниты, статус → paid.
        Продление: обновляет end_date родителя, статус продления → completed.

        Обёрнуто в transaction.atomic — при ошибке откатится вся операция.
        """
        # Перечитать бронирование с блокировкой
        booking = Booking.objects.select_for_update().get(pk=self.pk)

        if booking.status != self.Status.PENDING:
            return False

        if booking.is_expired:
            booking.cancel()
            return False

        booking.paid_at = timezone.now()
        booking.stripe_payment_id = payment_id
        if receipt_url:
            booking.stripe_receipt_url = receipt_url

        # Для lk_invoice фиксируем total_aed как сумму, реально полученную через
        # Stripe (для cash/stripe_payment_link менеджер ставит её сам при создании).
        if booking.payment_method == self.PaymentMethod.LK_INVOICE:
            booking.payment_amount_collected = booking.total_aed

        if booking.is_extension:
            parent = Booking.objects.select_for_update().get(pk=booking.parent_booking_id)
            parent.end_date = booking.end_date
            parent.save(update_fields=['end_date', 'updated_at'])
            booking.status = self.Status.COMPLETED
        else:
            booking.status = self.Status.PAID
            booking.assign_storage_units()

        booking.save()

        # Обновить self чтобы вызывающий код видел новые значения
        self.status = booking.status
        self.paid_at = booking.paid_at
        self.stripe_payment_id = booking.stripe_payment_id
        self.storage_unit = booking.storage_unit
        self.unit_codes = booking.unit_codes
        self.payment_amount_collected = booking.payment_amount_collected

        # Уведомление вне транзакции — не должно откатывать платёж
        try:
            from notifications.services import notify_booking_paid
            notify_booking_paid(booking)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Notification error: {e}")

        return True

    @transaction.atomic
    def complete_extension_externally_paid(self, amount_collected):
        """Завершить продление, оплаченное вне нашей системы (cash / stripe link).

        Используется только для extension (parent_booking != None). Юнит уже
        принадлежит родителю — мы только обновляем `parent.end_date` и помечаем
        extension как COMPLETED. Сумма пишется в payment_amount_collected
        для отчётности.
        """
        booking = Booking.objects.select_for_update().get(pk=self.pk)

        if not booking.is_extension or booking.status != self.Status.PENDING:
            return False

        booking.paid_at = timezone.now()
        booking.payment_amount_collected = amount_collected

        parent = Booking.objects.select_for_update().get(pk=booking.parent_booking_id)
        parent.end_date = booking.end_date
        parent.save(update_fields=['end_date', 'updated_at'])

        booking.status = self.Status.COMPLETED
        booking.save()

        self.status = booking.status
        self.paid_at = booking.paid_at
        self.payment_amount_collected = booking.payment_amount_collected

        try:
            from notifications.services import notify_booking_paid
            notify_booking_paid(booking)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Notification error: {e}")

        return True

    @transaction.atomic
    def activate_externally_paid(self, amount_collected, storage_unit=None):
        """Активировать бронирование, оплаченное вне нашей системы.

        Используется для cash и stripe_payment_link — деньги собирает менеджер,
        наша БД фиксирует факт и сумму для отчётности. Бронирование сразу
        получает статус PAID и юнит назначается (или используется указанный).
        """
        booking = Booking.objects.select_for_update().get(pk=self.pk)

        if booking.status != self.Status.PENDING:
            return False

        booking.paid_at = timezone.now()
        booking.payment_amount_collected = amount_collected
        booking.status = self.Status.PAID

        if storage_unit is not None:
            # Менеджер указал конкретный юнит — занимаем его напрямую
            from services.models import StorageUnit
            unit = StorageUnit.objects.select_for_update().get(pk=storage_unit.pk)
            if not unit.is_available or not unit.is_active:
                raise ValueError(f'Unit {unit.full_code} is not available')
            unit.is_available = False
            unit.save(update_fields=['is_available'])
            BookingUnit.objects.create(booking=booking, storage_unit=unit)
            booking.storage_unit = unit
            booking.unit_codes = unit.full_code
        else:
            booking.assign_storage_units()

        booking.save()

        self.status = booking.status
        self.paid_at = booking.paid_at
        self.payment_amount_collected = booking.payment_amount_collected
        self.storage_unit = booking.storage_unit
        self.unit_codes = booking.unit_codes

        try:
            from notifications.services import notify_booking_paid
            notify_booking_paid(booking)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Notification error: {e}")

        return True

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

    @transaction.atomic
    def reassign_unit(self, old_unit, new_unit):
        """Переселить бронирование с одного юнита на другой.

        Освобождает old_unit, занимает new_unit, обновляет BookingUnit,
        storage_unit (primary) и снепшот unit_codes.

        Атомарно: при ошибке между release old и occupy new откатится всё —
        не оставит юниты в inconsistent state.
        """
        if self.status != self.Status.PAID:
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
