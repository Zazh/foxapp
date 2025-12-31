import os
from io import BytesIO
from PIL import Image as PILImage
from django.core.files.base import ContentFile

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

class Service(models.Model):
    """Тип услуги: auto storage или storage"""

    class ServiceType(models.TextChoices):
        AUTO = 'auto', _('Auto storage')
        STORAGE = 'storage', _('Storage')

    service_type = models.CharField(
        max_length=20,
        choices=ServiceType.choices,
        unique=True,
        verbose_name=_('Service type')
    )
    name = models.CharField(max_length=255, verbose_name=_('Name'))
    description = models.TextField(blank=True, verbose_name=_('Description'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _('Service')
        verbose_name_plural = _('Services')

    def __str__(self):
        return self.name


class Tariff(models.Model):
    """Тариф, привязан к услуге и локации"""

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='tariffs',
        verbose_name=_('Service')
    )
    location = models.ForeignKey(
        'locations.Location',
        on_delete=models.CASCADE,
        related_name='tariffs',
        verbose_name=_('Location')
    )
    slug = models.SlugField(
        max_length=255,
        blank=True,
        verbose_name=_('Slug'),
        help_text=_('Auto-generated from English name')
    )
    name = models.CharField(max_length=255, verbose_name=_('Name'))
    title = models.CharField(max_length=255, blank=True, verbose_name=_('Title'))
    description = models.TextField(blank=True, verbose_name=_('Description'),
                                   help_text=_('HTML tags allowed: <strong>, <em>, etc.'))
    svg_icon = models.TextField(blank=True, verbose_name=_('SVG icon'), help_text=_('Full SVG code'))
    is_custom = models.BooleanField(default=False, verbose_name=_('Custom tariff'),
                                    help_text=_('Only visible to managers'))

    deposit_aed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_('Deposit (AED)')
    )

    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_units(self):
        """Всего мест для этого тарифа (по service + location)"""
        return StorageUnit.objects.filter(
            section__service=self.service,
            section__location=self.location,
            section__is_active=True,
            is_active=True
        ).count()

    @property
    def available_units(self):
        """Свободных мест"""
        return StorageUnit.objects.filter(
            section__service=self.service,
            section__location=self.location,
            section__is_active=True,
            is_active=True,
            is_available=True
        ).count()

    @property
    def availability_percent(self):
        """Процент свободных мест"""
        total = self.total_units
        if total == 0:
            return 0
        return int((self.available_units / total) * 100)

    @property
    def availability_status(self):
        """Статус: fully_booked / few_left / available"""
        if self.available_units == 0:
            return 'fully_booked'
        elif self.availability_percent <= 20:
            return 'few_left'
        return 'available'

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _('Tariff')
        verbose_name_plural = _('Tariffs')
        unique_together = ['service', 'location', 'slug']

    def __str__(self):
        return f"{self.name} — {self.location.name}"

    def save(self, *args, **kwargs):
        if not self.slug and self.name_en:
            base_slug = slugify(self.name_en)
            # Уникальный slug для комбинации service + location
            slug = base_slug
            counter = 1
            while Tariff.objects.filter(
                    slug=slug,
                    service=self.service,
                    location=self.location
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)



class TariffImage(models.Model):
    """Фотогалерея тарифа"""

    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_('Tariff')
    )
    image = models.ImageField(upload_to='tariffs/', verbose_name=_('Image'))
    alt_text = models.CharField(max_length=255, blank=True, verbose_name=_('Alt text'))
    is_cover = models.BooleanField(default=False, verbose_name=_('Cover image'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['-is_cover', 'sort_order']
        verbose_name = _('Tariff image')
        verbose_name_plural = _('Tariff images')

    def __str__(self):
        return f"Image for {self.tariff.name}"

    def save(self, *args, **kwargs):
        if self.image:
            self.image = self.compress_image(self.image)
        super().save(*args, **kwargs)

    def compress_image(self, image, max_width=700, quality=85):
        """Сжать и конвертировать в WebP"""
        img = PILImage.open(image)

        # Конвертировать в RGB если нужно (для PNG с прозрачностью)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Изменить размер если ширина больше max_width
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), PILImage.LANCZOS)

        # Сохранить в WebP
        output = BytesIO()
        img.save(output, format='WEBP', quality=quality, optimize=True)
        output.seek(0)

        # Новое имя файла с .webp
        filename = os.path.splitext(os.path.basename(image.name))[0]
        new_filename = f"{filename}.webp"

        return ContentFile(output.read(), name=new_filename)


class TariffSize(models.Model):
    """Размеры тарифа (Width, Height, Depth)"""

    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='sizes',
        verbose_name=_('Tariff')
    )
    label = models.CharField(max_length=100, verbose_name=_('Label'))  # Width, Height
    value = models.CharField(max_length=50, verbose_name=_('Value'))  # 2.5m, 3m
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Tariff size')
        verbose_name_plural = _('Tariff sizes')

    def __str__(self):
        return f"{self.label}: {self.value}"


class TariffPeriod(models.Model):
    """Период хранения с ценой"""

    class DurationType(models.TextChoices):
        DAYS = 'days', _('Days')
        MONTHS = 'months', _('Months')

    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='periods',
        verbose_name=_('Tariff')
    )
    name = models.CharField(max_length=100, verbose_name=_('Name'))
    description = models.TextField(blank=True, verbose_name=_('Description'))

    # Длительность
    duration_type = models.CharField(
        max_length=10,
        choices=DurationType.choices,
        default=DurationType.MONTHS,
        verbose_name=_('Duration type')
    )
    duration_value = models.PositiveIntegerField(
        verbose_name=_('Duration value'),
        help_text=_('Number of days or months')
    )

    # Цены (AED основная)
    price_aed = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Price (AED)'))
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Price (USD)'))

    # Старые цены для отображения скидки
    original_price_aed = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name=_('Original price (AED)')
    )
    original_price_usd = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name=_('Original price (USD)')
    )
    discount_label = models.CharField(
        max_length=100, blank=True,
        verbose_name=_('Discount label'),
        help_text=_('e.g., "Save 20%"')
    )

    is_custom = models.BooleanField(default=False, verbose_name=_('Custom period'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))

    is_recommended = models.BooleanField(
        default=False,
        verbose_name=_('Recommended'),
        help_text=_('Pre-selected by default on frontend')
    )

    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order', 'duration_value']
        verbose_name = _('Tariff period')
        verbose_name_plural = _('Tariff periods')

    def __str__(self):
        return f"{self.name} — {self.price_aed} AED"

    def calculate_end_date(self, start_date):
        """Рассчитать дату окончания"""
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta

        if self.duration_type == self.DurationType.DAYS:
            return start_date + timedelta(days=self.duration_value)
        else:  # months
            return start_date + relativedelta(months=self.duration_value)

    @property
    def duration_display(self):
        """Для отображения: '30 days' или '1 month'"""
        if self.duration_type == self.DurationType.DAYS:
            return f"{self.duration_value} {'day' if self.duration_value == 1 else 'days'}"
        else:
            return f"{self.duration_value} {'month' if self.duration_value == 1 else 'months'}"

    @property
    def has_discount(self):
        return self.original_price_aed is not None and self.original_price_aed > self.price_aed

    @property
    def discount_percent(self):
        if self.has_discount:
            return int(100 - (self.price_aed / self.original_price_aed * 100))
        return 0


class TariffBenefit(models.Model):
    """Преимущества тарифа (list)"""

    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='benefits',
        verbose_name=_('Tariff')
    )
    text = models.CharField(max_length=255, verbose_name=_('Text'))
    icon = models.CharField(max_length=100, blank=True, verbose_name=_('Icon class'), help_text=_('CSS class for icon'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Tariff benefit')
        verbose_name_plural = _('Tariff benefits')

    def __str__(self):
        return self.text


class TariffImage(models.Model):
    """Фотогалерея тарифа"""

    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_('Tariff')
    )
    image = models.ImageField(upload_to='tariffs/', verbose_name=_('Image'))
    alt_text = models.CharField(max_length=255, blank=True, verbose_name=_('Alt text'))
    is_cover = models.BooleanField(default=False, verbose_name=_('Cover image'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['-is_cover', 'sort_order']
        verbose_name = _('Tariff image')
        verbose_name_plural = _('Tariff images')

    def __str__(self):
        return f"Image for {self.tariff.name}"


class AddonService(models.Model):
    """Дополнительные услуги"""

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='addons',
        verbose_name=_('Service')
    )
    name = models.CharField(max_length=255, verbose_name=_('Name'))
    description = models.TextField(blank=True, verbose_name=_('Description'))
    price_aed = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Price (AED)'))
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Price (USD)'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _('Addon service')
        verbose_name_plural = _('Addon services')

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return self.price_aed == 0


class Section(models.Model):
    """Секция на локации (A, B, VIP)"""

    location = models.ForeignKey(
        'locations.Location',
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name=_('Location')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name=_('Service')
    )
    name = models.CharField(max_length=100, verbose_name=_('Name'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Sort order'))

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _('Section')
        verbose_name_plural = _('Sections')
        unique_together = ['location', 'service', 'name']

    def __str__(self):
        return f"{self.location.name} — {self.name}"


class StorageUnit(models.Model):
    """Место для аренды"""

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='units',
        verbose_name=_('Section')
    )
    unit_number = models.CharField(max_length=50, verbose_name=_('Unit number'))
    is_available = models.BooleanField(default=True, verbose_name=_('Available'), help_text=_('Available for booking'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'), help_text=_('Active in system'))

    class Meta:
        ordering = ['section', 'unit_number']
        verbose_name = _('Storage unit')
        verbose_name_plural = _('Storage units')
        unique_together = ['section', 'unit_number']

    def __str__(self):
        return f"{self.section.name}-{self.unit_number}"

    @property
    def full_code(self):
        """Полный код места: Location-Section-Number"""
        return f"{self.section.location.name[:3].upper()}-{self.section.name}-{self.unit_number}"

    @property
    def current_booking(self):
        """Текущее активное бронирование"""
        return self.bookings.filter(
            status__in=['paid', 'active']
        ).select_related('user').first()