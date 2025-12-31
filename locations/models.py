# locations/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _


class Location(models.Model):
    """Филиал/локация"""

    class LocationType(models.TextChoices):
        AUTO_STORAGE = 'auto', _('Auto storage')
        STORAGE = 'storage', _('Storage')
        HEAD_OFFICE = 'headoffice', _('Head office')

    # Тип локации
    location_type = models.CharField(
        _('location type'),
        max_length=20,
        choices=LocationType.choices,
        default=LocationType.STORAGE,
    )

    # Мультиязычные поля
    name = models.CharField(_('name'), max_length=255)
    street = models.CharField(_('street'), max_length=255)
    building = models.CharField(_('building'), max_length=50)
    description = models.TextField(_('description'), blank=True)
    working_hours = models.CharField(_('working hours'), max_length=255, help_text=_('e.g. Sun-Thu 9:00-18:00'))

    # Обычные поля
    phone = models.CharField(_('phone'), max_length=20, blank=True)
    email = models.EmailField(_('email'), blank=True)

    # Координаты
    latitude = models.DecimalField(_('latitude'), max_digits=10, decimal_places=7)
    longitude = models.DecimalField(_('longitude'), max_digits=10, decimal_places=7)

    # Статус и сортировка
    is_active = models.BooleanField(_('active'), default=True)
    sort_order = models.PositiveIntegerField(_('sort order'), default=0)

    # Даты
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('location')
        verbose_name_plural = _('locations')
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.get_location_type_display()} - {self.name}"

    @property
    def coordinates(self):
        """Для data-coordinates в шаблоне"""
        return f"{self.latitude},{self.longitude}"

    @property
    def google_maps_url(self):
        """Ссылка на маршрут в Google Maps"""
        return f"https://www.google.com/maps/dir/?api=1&destination={self.latitude},{self.longitude}&travelmode=driving"

    @property
    def full_address(self):
        """Полный адрес"""
        return f"{self.street}, {self.building}"