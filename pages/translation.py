from modeltranslation.translator import translator, TranslationOptions
from .models import (
    HomePage, HomeBenefit, HomeGallerySlide, HomeDashboardFeature,
    AboutPage, AboutOfferItem, ContactsPage, ContactInfoItem, FeedbackCTA,
)


class HomePageTranslationOptions(TranslationOptions):
    fields = (
        'hero_title_line1',
        'hero_title_line2',
        'hero_title_line3',
        'hero_subtitle',
        'hero_cta_primary_text',
        'hero_cta_secondary_text',
        'benefits_title',
        'benefits_subtitle',
        'benefits_cta_text',
        'gallery_title',
        'gallery_subtitle',
        'dashboard_title',
        'dashboard_subtitle',
    )


class HomeBenefitTranslationOptions(TranslationOptions):
    fields = ('title', 'description')


class HomeGallerySlideTranslationOptions(TranslationOptions):
    fields = ('alt_text', 'caption')


class HomeDashboardFeatureTranslationOptions(TranslationOptions):
    fields = ('text',)


translator.register(HomePage, HomePageTranslationOptions)
translator.register(HomeBenefit, HomeBenefitTranslationOptions)
translator.register(HomeGallerySlide, HomeGallerySlideTranslationOptions)
translator.register(HomeDashboardFeature, HomeDashboardFeatureTranslationOptions)


class AboutPageTranslationOptions(TranslationOptions):
    fields = (
        'hero_label',
        'hero_title',
        'hero_subtitle',
        'hero_block_title',
        'hero_block_text',
        'hero_image_alt',
        'offers_label',
        'offers_title',
        'offers_description',
        'offers_text',
        'offers_closing',
    )


class AboutOfferItemTranslationOptions(TranslationOptions):
    fields = ('text',)


translator.register(AboutPage, AboutPageTranslationOptions)
translator.register(AboutOfferItem, AboutOfferItemTranslationOptions)


class ContactsPageTranslationOptions(TranslationOptions):
    fields = (
        'hero_label',
        'hero_title',
        'hero_subtitle',
    )


class ContactInfoItemTranslationOptions(TranslationOptions):
    fields = ('label', 'value')


translator.register(ContactsPage, ContactsPageTranslationOptions)
translator.register(ContactInfoItem, ContactInfoItemTranslationOptions)


class FeedbackCTATranslationOptions(TranslationOptions):
    fields = ('title', 'cta_text')


translator.register(FeedbackCTA, FeedbackCTATranslationOptions)


from .models import NavLink


class NavLinkTranslationOptions(TranslationOptions):
    fields = ('title',)


translator.register(NavLink, NavLinkTranslationOptions)
