from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline

from .models import (
    Service,
    Tariff,
    TariffSize,
    TariffPeriod,
    TariffBenefit,
    TariffImage,
    AddonService,
    Section,
    StorageUnit,
)


# ============ INLINES ============

class TariffSizeInline(TranslationTabularInline):
    model = TariffSize
    extra = 0
    fields = ('label', 'value', 'sort_order')


class TariffPeriodInline(TranslationTabularInline):
    model = TariffPeriod
    extra = 0
    fields = (
        'name', 'duration_type', 'duration_value',
        'price_aed', 'price_usd',
        'original_price_aed', 'original_price_usd',
        'discount_label', 'is_recommended', 'is_custom', 'is_active', 'sort_order'
    )


class TariffBenefitInline(TranslationTabularInline):
    model = TariffBenefit
    extra = 0
    fields = ('text', 'icon', 'sort_order')


class TariffImageInline(admin.TabularInline):
    model = TariffImage
    extra = 0
    fields = ('image', 'image_preview', 'alt_text', 'is_cover', 'sort_order')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px;"/>', obj.image.url)
        return '-'

    image_preview.short_description = _('Preview')


class AddonServiceInline(TranslationTabularInline):
    model = AddonService
    extra = 0
    fields = ('name', 'description', 'price_aed', 'price_usd', 'is_active', 'sort_order')


class StorageUnitInline(admin.TabularInline):
    model = StorageUnit
    extra = 0
    fields = ('unit_number', 'is_available', 'is_active')


# ============ MAIN ADMINS ============

@admin.register(Service)
class ServiceAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'service_type', 'is_active', 'sort_order')
    list_filter = ('service_type', 'is_active')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')

    fieldsets = (
        (None, {
            'fields': ('service_type', 'name', 'description')
        }),
        (_('Settings'), {
            'fields': ('is_active', 'sort_order')
        }),
    )

    inlines = [AddonServiceInline]


@admin.register(Tariff)
class TariffAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'slug', 'service', 'location', 'is_custom', 'is_active', 'sort_order')
    list_filter = ('service', 'location', 'is_custom', 'is_active')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'slug', 'title', 'description')
    ordering = ('service', 'location', 'sort_order')
    autocomplete_fields = ('service', 'location')
    prepopulated_fields = {'slug': ('name_en',)}

    fieldsets = (
        (None, {
            'fields': ('service', 'location')
        }),
        (_('Content'), {
            'fields': ('name', 'slug', 'title', 'description', 'svg_icon')
        }),
        (_('Pricing'), {
            'fields': ('deposit_aed',)
        }),
        (_('Settings'), {
            'fields': ('is_custom', 'is_active', 'sort_order')
        }),
    )

    inlines = [TariffSizeInline, TariffPeriodInline, TariffBenefitInline, TariffImageInline]


@admin.register(TariffPeriod)
class TariffPeriodAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'tariff', 'duration_type', 'duration_value', 'price_aed', 'price_usd', 'is_recommended',
                    'is_custom', 'is_active')
    list_filter = ('tariff__service', 'duration_type', 'is_recommended', 'is_custom', 'is_active')
    list_editable = ('is_recommended', 'is_active',)
    search_fields = ('name', 'tariff__name')
    ordering = ('tariff', 'sort_order')
    autocomplete_fields = ('tariff',)

    fieldsets = (
        (None, {
            'fields': ('tariff', 'name', 'description')
        }),
        (_('Duration'), {
            'fields': (('duration_type', 'duration_value'),)
        }),
        (_('Pricing'), {
            'fields': (
                ('price_aed', 'price_usd'),
                ('original_price_aed', 'original_price_usd'),
                'discount_label'
            )
        }),
        (_('Settings'), {
            'fields': ('is_recommended', 'is_custom', 'is_active', 'sort_order')
        }),
    )

@admin.register(AddonService)
class AddonServiceAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'service', 'price_aed', 'price_usd', 'is_free_display', 'is_active', 'sort_order')
    list_filter = ('service', 'is_active')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'description')
    ordering = ('service', 'sort_order')
    autocomplete_fields = ('service',)

    fieldsets = (
        (None, {
            'fields': ('service', 'name', 'description')
        }),
        (_('Pricing'), {
            'fields': (('price_aed', 'price_usd'),)
        }),
        (_('Settings'), {
            'fields': ('is_active', 'sort_order')
        }),
    )

    def is_free_display(self, obj):
        return obj.is_free

    is_free_display.boolean = True
    is_free_display.short_description = _('Free')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'service', 'units_count', 'available_count', 'is_active', 'sort_order')
    list_filter = ('location', 'service', 'is_active')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'location__name')
    ordering = ('location', 'service', 'sort_order')
    autocomplete_fields = ('location', 'service')

    fieldsets = (
        (None, {
            'fields': ('location', 'service', 'name')
        }),
        (_('Settings'), {
            'fields': ('is_active', 'sort_order')
        }),
    )

    inlines = [StorageUnitInline]

    def units_count(self, obj):
        return obj.units.filter(is_active=True).count()

    units_count.short_description = _('Total units')

    def available_count(self, obj):
        return obj.units.filter(is_active=True, is_available=True).count()

    available_count.short_description = _('Available')


@admin.register(StorageUnit)
class StorageUnitAdmin(admin.ModelAdmin):
    list_display = ('full_code', 'section', 'unit_number', 'is_available', 'is_active')
    list_filter = ('section__location', 'section__service', 'section', 'is_available', 'is_active')
    list_editable = ('is_available', 'is_active')
    search_fields = ('unit_number', 'section__name', 'section__location__name')
    ordering = ('section', 'unit_number')
    autocomplete_fields = ('section',)

    fieldsets = (
        (None, {
            'fields': ('section', 'unit_number')
        }),
        (_('Status'), {
            'fields': (('is_available', 'is_active'),)
        }),
    )