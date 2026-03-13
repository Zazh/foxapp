from modeltranslation.translator import translator, TranslationOptions
from .models import (
    Service,
    Tariff,
    TariffSize,
    TariffPeriod,
    TariffBenefit,
    TariffImage,
    AddonService,
)


class ServiceTranslationOptions(TranslationOptions):
    fields = ('name', 'description', 'quantity_label', 'addons_label')


class TariffTranslationOptions(TranslationOptions):
    fields = ('name', 'title', 'description')


class TariffSizeTranslationOptions(TranslationOptions):
    fields = ('label', 'value')


class TariffPeriodTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class TariffBenefitTranslationOptions(TranslationOptions):
    fields = ('text',)


class TariffImageTranslationOptions(TranslationOptions):
    fields = ('alt_text',)


class AddonServiceTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


translator.register(Service, ServiceTranslationOptions)
translator.register(Tariff, TariffTranslationOptions)
translator.register(TariffSize, TariffSizeTranslationOptions)
translator.register(TariffPeriod, TariffPeriodTranslationOptions)
translator.register(TariffBenefit, TariffBenefitTranslationOptions)
translator.register(TariffImage, TariffImageTranslationOptions)
translator.register(AddonService, AddonServiceTranslationOptions)