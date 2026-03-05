from django.contrib import admin
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from .models import (
    HomePage, HomeBenefit, HomeGallerySlide, HomeDashboardFeature,
    AboutPage, AboutOfferItem, ContactsPage, ContactInfoItem, FeedbackCTA,
)


class HomeBenefitInline(TranslationTabularInline):
    model = HomeBenefit
    extra = 0
    fields = ('title', 'description', 'svg_icon', 'sort_order')


class HomeGallerySlideInline(TranslationTabularInline):
    model = HomeGallerySlide
    extra = 0
    fields = ('image', 'alt_text', 'caption', 'sort_order')


class HomeDashboardFeatureInline(TranslationTabularInline):
    model = HomeDashboardFeature
    extra = 0
    fields = ('text', 'svg_icon', 'bg_color', 'sort_order')


@admin.register(HomePage)
class HomePageAdmin(TabbedTranslationAdmin):
    fieldsets = (
        ('Hero Section', {
            'fields': (
                'hero_title_line1',
                'hero_title_line2',
                'hero_title_line3',
                'hero_subtitle',
                'hero_cta_primary_text',
                'hero_cta_primary_url',
                'hero_cta_secondary_text',
            ),
        }),
        ('Benefits Section', {
            'fields': (
                'benefits_title',
                'benefits_subtitle',
                'benefits_cta_text',
            ),
        }),
        ('Gallery Section', {
            'fields': (
                'gallery_title',
                'gallery_subtitle',
            ),
        }),
        ('Dashboard Section', {
            'fields': (
                'dashboard_title',
                'dashboard_subtitle',
            ),
        }),
    )
    inlines = [HomeBenefitInline, HomeGallerySlideInline, HomeDashboardFeatureInline]

    def has_add_permission(self, request):
        return not HomePage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class AboutOfferItemInline(TranslationTabularInline):
    model = AboutOfferItem
    extra = 0
    fields = ('text', 'sort_order')


@admin.register(AboutPage)
class AboutPageAdmin(TabbedTranslationAdmin):
    fieldsets = (
        ('Hero Section', {
            'fields': (
                'hero_label',
                'hero_title',
                'hero_subtitle',
                'hero_block_title',
                'hero_block_text',
                'hero_image',
                'hero_image_alt',
            ),
        }),
        ('Offers Section', {
            'fields': (
                'offers_label',
                'offers_title',
                'offers_description',
                'offers_text',
                'offers_closing',
            ),
        }),
    )
    inlines = [AboutOfferItemInline]

    def has_add_permission(self, request):
        return not AboutPage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class ContactInfoItemInline(TranslationTabularInline):
    model = ContactInfoItem
    extra = 0
    fields = ('label', 'value', 'sort_order')


@admin.register(ContactsPage)
class ContactsPageAdmin(TabbedTranslationAdmin):
    fieldsets = (
        ('Hero Section', {
            'fields': (
                'hero_label',
                'hero_title',
                'hero_subtitle',
            ),
        }),
    )
    inlines = [ContactInfoItemInline]

    def has_add_permission(self, request):
        return not ContactsPage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeedbackCTA)
class FeedbackCTAAdmin(TabbedTranslationAdmin):
    fields = ('title', 'cta_text')

    def has_add_permission(self, request):
        return not FeedbackCTA.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
