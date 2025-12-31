# locations/translation.py
from modeltranslation.translator import translator, TranslationOptions
from .models import Location


class LocationTranslationOptions(TranslationOptions):
    fields = ('name', 'street', 'building', 'description', 'working_hours')


translator.register(Location, LocationTranslationOptions)