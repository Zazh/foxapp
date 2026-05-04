from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from bookings.models import Booking
from services.models import Tariff, TariffPeriod, StorageUnit

User = get_user_model()


class ManagerUserCreateForm(forms.Form):
    """Менеджер создаёт нового клиента "под ключ"."""

    email = forms.EmailField(label=_('Email'))
    first_name = forms.CharField(label=_('First name'), max_length=150)
    last_name = forms.CharField(label=_('Last name'), max_length=150, required=False)
    phone = forms.CharField(label=_('Phone'), max_length=20, required=False)
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput,
        help_text=_('You will share this with the customer (e.g. via WhatsApp).'),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        validate_password(password)
        return password

    def save(self):
        user = User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data.get('last_name', ''),
            phone=self.cleaned_data.get('phone', ''),
            id_card=None,
        )
        user.auth_provider = 'email'
        user.is_verified = True
        user.save(update_fields=['auth_provider', 'is_verified'])
        return user


class ManagerBookingCreateForm(forms.Form):
    """Менеджер создаёт бронирование от имени клиента.

    UX-логика:
    - Клиент выбирается через autocomplete (поле user_id, скрытое — JS заполнит).
    - Тариф: dropdown; если тариф один, JS выбирает его автоматически.
    - period_type=standard → выбираем TariffPeriod, цена авто из тарифа,
      опционально override.
    - period_type=custom → ручные start/end + ручная цена.
    - quantity показывается только если у service есть quantity_label.
    - storage_unit: пусто = авто-выбор первой свободной.
    """

    PERIOD_TYPE_STANDARD = 'standard'
    PERIOD_TYPE_CUSTOM = 'custom'
    PERIOD_TYPE_CHOICES = [
        (PERIOD_TYPE_STANDARD, _('Standard period')),
        (PERIOD_TYPE_CUSTOM, _('Custom dates & price')),
    ]

    user_id = forms.IntegerField(widget=forms.HiddenInput)
    tariff = forms.ModelChoiceField(
        label=_('Tariff'),
        queryset=Tariff.objects.filter(is_active=True).select_related('service', 'location'),
    )
    period_type = forms.ChoiceField(
        choices=PERIOD_TYPE_CHOICES,
        initial=PERIOD_TYPE_STANDARD,
        widget=forms.HiddenInput,  # Управляется табами
    )
    period = forms.ModelChoiceField(
        label=_('Period'),
        queryset=TariffPeriod.objects.filter(is_active=True),
        required=False,
    )
    quantity = forms.IntegerField(
        label=_('Quantity'),
        min_value=1,
        initial=1,
    )
    # Queryset = ВСЕ активные юниты (включая занятые), потому что менеджер
    # может выбрать "текущий юнит клиента" — это превращает форму в extension.
    # JS добавляет такую опцию динамически после выбора клиента.
    # Валидация в clean(): занятый юнит должен принадлежать выбранному клиенту.
    storage_unit = forms.ModelChoiceField(
        label=_('Specific unit'),
        queryset=StorageUnit.objects.filter(is_active=True),
        required=False,
        empty_label=_('— Auto-select first available —'),
    )

    custom_start_date = forms.DateField(
        label=_('Start date'),
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    custom_end_date = forms.DateField(
        label=_('End date'),
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    override_price = forms.BooleanField(
        label=_('Override standard price'),
        required=False,
    )
    price_aed = forms.DecimalField(
        label=_('Price (AED)'),
        max_digits=10, decimal_places=2,
        required=False,
        help_text=_('Total price for the booking (no deposit).'),
    )

    payment_method = forms.ChoiceField(
        label=_('Payment method'),
        choices=Booking.PaymentMethod.choices,
        initial=Booking.PaymentMethod.STRIPE_PAYMENT_LINK,
    )

    def clean_user_id(self):
        user_id = self.cleaned_data.get('user_id')
        if not user_id:
            raise forms.ValidationError(_('Customer is required.'))
        if not User.objects.filter(pk=user_id).exists():
            raise forms.ValidationError(_('Customer not found.'))
        return user_id

    def clean(self):
        cleaned = super().clean()
        period_type = cleaned.get('period_type')
        period = cleaned.get('period')
        custom_start = cleaned.get('custom_start_date')
        custom_end = cleaned.get('custom_end_date')
        override = cleaned.get('override_price')
        manual_price = cleaned.get('price_aed')

        if period_type == self.PERIOD_TYPE_STANDARD:
            if not period:
                self.add_error('period', _('Select a period.'))
            if override and manual_price is None:
                self.add_error('price_aed', _('Enter the override price.'))
        elif period_type == self.PERIOD_TYPE_CUSTOM:
            if not custom_start:
                self.add_error('custom_start_date', _('Required for custom dates.'))
            if not custom_end:
                self.add_error('custom_end_date', _('Required for custom dates.'))
            if custom_start and custom_end and custom_end <= custom_start:
                self.add_error('custom_end_date', _('End must be after start.'))
            if manual_price is None:
                self.add_error('price_aed', _('Enter the price for custom dates.'))

        # При quantity > 1 выбор конкретного юнита бессмысленен — система должна
        # авто-назначить N свободных. Defensive guard на случай, если форма
        # пришла в обход JS (multi-unit + specific unit).
        unit = cleaned.get('storage_unit')
        quantity = cleaned.get('quantity') or 1
        tariff = cleaned.get('tariff')
        if unit and quantity > 1:
            self.add_error(
                'storage_unit',
                _('Cannot pick a specific unit when quantity is greater than 1 — units are auto-assigned.'),
            )
            unit = None  # Не идём дальше с inconsistent state

        # Нельзя запросить больше юнитов, чем реально свободно у тарифа.
        # Extension всегда qty=1, так что эта проверка касается только новой брони.
        if quantity > 1 and tariff:
            available = tariff.available_units
            if quantity > available:
                self.add_error(
                    'quantity',
                    _('Only %(n)d unit(s) are currently available.') % {'n': available},
                )

        # Юнит выбран и занят — проверяем, что он принадлежит выбранному клиенту
        # как primary unit активной брони. Иначе менеджер случайно занимает чужой юнит.
        user_id = cleaned.get('user_id')
        if unit and not unit.is_available and user_id:
            owned = Booking.objects.filter(
                user_id=user_id,
                storage_unit=unit,
                parent_booking__isnull=True,
                status=Booking.Status.PAID,
            ).exists()
            if not owned:
                self.add_error(
                    'storage_unit',
                    _('This unit is occupied by another customer.'),
                )

        return cleaned
