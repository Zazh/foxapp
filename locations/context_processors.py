# locations/context_processors.py
from .models import Location


def locations(request):
    """Добавляет локации во все шаблоны"""
    active_locations = Location.objects.filter(is_active=True)

    return {
        'locations': active_locations,
        'locations_auto': active_locations.filter(location_type='auto'),
        'locations_storage': active_locations.filter(location_type='storage'),
        'locations_headoffice': active_locations.filter(location_type='headoffice'),
        'primary_location': active_locations.first(),
    }