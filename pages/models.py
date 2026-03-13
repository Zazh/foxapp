import os
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models
from django.utils.translation import gettext_lazy as _
from PIL import Image as PILImage


def compress_to_webp(image, max_width=1920, quality=85):
    """Compress image to WebP format."""
    img = PILImage.open(image)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), PILImage.LANCZOS)
    output = BytesIO()
    img.save(output, format='WEBP', quality=quality, optimize=True)
    output.seek(0)
    filename = os.path.splitext(os.path.basename(image.name))[0]
    return ContentFile(output.read(), name=f'{filename}.webp')


class HomePage(models.Model):
    """Singleton model for home page content"""

    # === Hero Section ===
    hero_title_line1 = models.CharField(
        _('Hero title (line 1)'),
        max_length=255,
        help_text=_('e.g. "Secure Car"'),
    )
    hero_title_line2 = models.CharField(
        _('Hero title (before logo)'),
        max_length=255,
        help_text=_('e.g. "Storage"'),
    )
    hero_title_line3 = models.CharField(
        _('Hero title (after logo)'),
        max_length=255,
        default='',
        help_text=_('e.g. "in Dubai"'),
    )
    hero_subtitle = models.TextField(
        _('Hero subtitle'),
        help_text=_('Text below the title'),
    )
    hero_cta_primary_text = models.CharField(
        _('Primary button text'),
        max_length=100,
        help_text=_('e.g. "Reserve your spot"'),
    )
    hero_cta_primary_url = models.CharField(
        _('Primary button URL'),
        max_length=255,
        blank=True,
        help_text=_('Leave blank to use default tariff link'),
    )
    hero_cta_secondary_text = models.CharField(
        _('Secondary button text'),
        max_length=100,
        help_text=_('e.g. "Show locations"'),
    )

    # === Benefits Section ===
    benefits_title = models.CharField(
        _('Benefits title'),
        max_length=255,
        default='',
        help_text=_('e.g. "Free up space"'),
    )
    benefits_subtitle = models.TextField(
        _('Benefits subtitle'),
        default='',
        blank=True,
        help_text=_('HTML allowed'),
    )
    benefits_cta_text = models.CharField(
        _('Benefits button text'),
        max_length=100,
        default='',
        help_text=_('e.g. "Reserve your spot"'),
    )

    # === Gallery Section ===
    gallery_title = models.CharField(
        _('Gallery title'),
        max_length=255,
        default='',
    )
    gallery_subtitle = models.TextField(
        _('Gallery subtitle'),
        default='',
        blank=True,
    )

    # === Dashboard Section ===
    dashboard_title = models.CharField(
        _('Dashboard title'),
        max_length=255,
        default='',
    )
    dashboard_subtitle = models.TextField(
        _('Dashboard subtitle'),
        default='',
        blank=True,
        help_text=_('HTML allowed'),
    )


    class Meta:
        verbose_name = _('Home Page')
        verbose_name_plural = _('Home Page')

    def __str__(self):
        return 'Home Page'

    def save(self, *args, **kwargs):
        if not self.pk and HomePage.objects.exists():
            raise ValueError('Only one HomePage instance is allowed.')
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'hero_title_line1': 'Secure Car',
                'hero_title_line2': 'Storage',
                'hero_title_line3': 'in Dubai',
                'hero_subtitle': (
                    'Transparent pricing, fast sign-up, secure parking, '
                    'and easy booking with flexible renewals '
                    '— with 24/7 access options'
                ),
                'hero_cta_primary_text': 'Reserve your spot',
                'hero_cta_secondary_text': 'Show locations',
                'benefits_title': 'Free up space',
                'benefits_cta_text': 'Reserve your spot',
            }
        )
        return obj


class HomeBenefit(models.Model):
    """Benefit card on home page"""

    page = models.ForeignKey(
        HomePage,
        on_delete=models.CASCADE,
        related_name='benefits',
        verbose_name=_('Page'),
    )
    title = models.CharField(_('Title'), max_length=255)
    description = models.CharField(_('Description'), max_length=500)
    svg_icon = models.TextField(
        _('SVG icon'),
        blank=True,
        help_text=_('Full SVG code'),
    )
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Benefit')
        verbose_name_plural = _('Benefits')

    def __str__(self):
        return self.title


class HomeGallerySlide(models.Model):
    """Gallery slide on home page"""

    page = models.ForeignKey(
        HomePage,
        on_delete=models.CASCADE,
        related_name='gallery_slides',
        verbose_name=_('Page'),
    )
    image = models.ImageField(_('Image'), upload_to='pages/gallery/')
    alt_text = models.CharField(_('Alt text'), max_length=255, blank=True)
    caption = models.CharField(_('Caption'), max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Gallery slide')
        verbose_name_plural = _('Gallery slides')

    def __str__(self):
        return self.alt_text or f'Slide {self.sort_order}'

    def save(self, *args, **kwargs):
        if self.image and not self.image.name.endswith('.webp'):
            self.image = compress_to_webp(self.image)
        super().save(*args, **kwargs)


class HomeDashboardFeature(models.Model):
    """Dashboard feature card on home page"""

    COLOR_CHOICES = [
        ('bg-blue-600', 'Blue'),
        ('bg-orange-500', 'Orange'),
        ('bg-black', 'Black'),
    ]

    page = models.ForeignKey(
        HomePage,
        on_delete=models.CASCADE,
        related_name='dashboard_features',
        verbose_name=_('Page'),
    )
    text = models.CharField(_('Text'), max_length=500)
    svg_icon = models.TextField(
        _('SVG icon'),
        blank=True,
        help_text=_('Full SVG code'),
    )
    bg_color = models.CharField(
        _('Background color'),
        max_length=50,
        choices=COLOR_CHOICES,
        default='bg-blue-600',
    )
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Dashboard feature')
        verbose_name_plural = _('Dashboard features')

    def __str__(self):
        return self.text[:50]


class AboutPage(models.Model):
    """Singleton model for about page content"""

    # === Hero Section ===
    hero_label = models.CharField(
        _('Hero sidebar label'),
        max_length=100,
        default='About',
    )
    hero_title = models.CharField(
        _('Hero title'),
        max_length=255,
        default='',
        help_text=_('e.g. "A&M Foxbox"'),
    )
    hero_subtitle = models.TextField(
        _('Hero subtitle'),
        default='',
        help_text=_('HTML allowed, orange text'),
    )
    hero_block_title = models.CharField(
        _('Hero block title'),
        max_length=255,
        default='',
        help_text=_('e.g. "What we offer"'),
    )
    hero_block_text = models.TextField(
        _('Hero block text'),
        default='',
    )
    hero_image = models.ImageField(
        _('Hero image'),
        upload_to='pages/about/',
        blank=True,
    )
    hero_image_alt = models.CharField(
        _('Hero image alt text'),
        max_length=255,
        default='foxbox',
    )

    # === Offers Section ===
    offers_label = models.CharField(
        _('Offers sidebar label'),
        max_length=100,
        default='Offers',
    )
    offers_title = models.CharField(
        _('Offers title'),
        max_length=255,
        default='',
    )
    offers_description = models.TextField(
        _('Offers description'),
        default='',
    )
    offers_text = models.TextField(
        _('Offers text'),
        default='',
        help_text=_('Text above the list'),
    )
    offers_closing = models.TextField(
        _('Offers closing text'),
        default='',
        help_text=_('Bold text below the list'),
    )

    class Meta:
        verbose_name = _('About Page')
        verbose_name_plural = _('About Page')

    def __str__(self):
        return 'About Page'

    def save(self, *args, **kwargs):
        if not self.pk and AboutPage.objects.exists():
            raise ValueError('Only one AboutPage instance is allowed.')
        if self.hero_image and not self.hero_image.name.endswith('.webp'):
            self.hero_image = compress_to_webp(self.hero_image)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'hero_label': 'About',
                'hero_title': 'A&M Foxbox',
                'hero_subtitle': (
                    'Foxbox is a premium car storage '
                    '<span class="md:block">facility located in Dubai.</span>'
                ),
                'hero_block_title': 'What we offer',
                'hero_block_text': (
                    'We provide secure, professionally managed indoor storage '
                    'for vehicles, designed for owners who value protection, '
                    'privacy, and peace of mind.'
                ),
                'hero_image_alt': 'foxbox',
                'offers_label': 'Offers',
                'offers_title': 'Our facility offers',
                'offers_description': (
                    'Foxbox is built for car enthusiasts, collectors, seasonal '
                    'residents, and owners who want their vehicle protected '
                    'when not in use'
                ),
                'offers_text': (
                    'Every vehicle stored at FOXBOX is treated with care and '
                    'handled with responsibility. Our focus is simple — safety, '
                    'discretion, and high standards.'
                ),
                'offers_closing': 'Your car. Properly stored. Properly protected',
            }
        )
        return obj


class AboutOfferItem(models.Model):
    """Offer list item on about page"""

    page = models.ForeignKey(
        AboutPage,
        on_delete=models.CASCADE,
        related_name='offer_items',
        verbose_name=_('Page'),
    )
    text = models.CharField(_('Text'), max_length=255)
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Offer item')
        verbose_name_plural = _('Offer items')

    def __str__(self):
        return self.text


class ContactsPage(models.Model):
    """Singleton model for contacts page content"""

    # === Hero Section ===
    hero_label = models.CharField(
        _('Hero sidebar label'),
        max_length=100,
        default='Contact',
    )
    hero_title = models.CharField(
        _('Hero title'),
        max_length=255,
        default='',
    )
    hero_subtitle = models.TextField(
        _('Hero subtitle'),
        default='',
    )

    class Meta:
        verbose_name = _('Contacts Page')
        verbose_name_plural = _('Contacts Page')

    def __str__(self):
        return 'Contacts Page'

    def save(self, *args, **kwargs):
        if not self.pk and ContactsPage.objects.exists():
            raise ValueError('Only one ContactsPage instance is allowed.')
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'hero_label': 'Contact',
                'hero_title': 'Contact us',
                'hero_subtitle': (
                    'Have a question about storage, access, or billing? '
                    'Reach out to our team — we\'ll help you choose the right '
                    'unit and answer any service questions.'
                ),
            }
        )
        return obj


class ContactInfoItem(models.Model):
    """Company info item on contacts page"""

    page = models.ForeignKey(
        ContactsPage,
        on_delete=models.CASCADE,
        related_name='info_items',
        verbose_name=_('Page'),
    )
    label = models.CharField(_('Label'), max_length=255)
    value = models.TextField(_('Value'))
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Info item')
        verbose_name_plural = _('Info items')

    def __str__(self):
        return self.label


class NavLink(models.Model):
    """Navigation link for header/sidebar/footer"""

    PAGE_CHOICES = [
        ('home', _('Home')),
        ('about', _('About')),
        ('contacts', _('Contacts')),
        ('custom', _('Custom URL')),
    ]

    title = models.CharField(_('Title'), max_length=100)
    page = models.CharField(
        _('Page'), max_length=50, choices=PAGE_CHOICES, default='custom',
    )
    custom_url = models.CharField(
        _('Custom URL'), max_length=500, blank=True, default='',
        help_text=_('Only for "Custom URL" page type, e.g. /services/auto/standard/'),
    )
    open_in_new_tab = models.BooleanField(_('Open in new tab'), default=False)
    is_active = models.BooleanField(_('Active'), default=True)
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Navigation link')
        verbose_name_plural = _('Navigation links')

    def __str__(self):
        return self.title

    def get_url(self):
        if self.page == 'custom':
            return self.custom_url
        from django.urls import reverse
        return reverse(self.page)

    def is_current(self, request):
        url = self.get_url()
        if not url:
            return False
        # Strip language prefix for comparison
        path = request.path
        if self.page == 'home':
            return path == url or path.rstrip('/') == url.rstrip('/')
        return path.startswith(url)


class SocialLink(models.Model):
    """Social media link for footer"""

    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('threads', 'Threads'),
        ('whatsapp', 'WhatsApp'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('telegram', 'Telegram'),
        ('facebook', 'Facebook'),
        ('x', 'X (Twitter)'),
    ]

    platform = models.CharField(
        _('Platform'),
        max_length=20,
        choices=PLATFORM_CHOICES,
    )
    url = models.URLField(_('URL'), max_length=500)
    is_active = models.BooleanField(_('Active'), default=True)
    sort_order = models.PositiveIntegerField(_('Sort order'), default=0)

    class Meta:
        ordering = ['sort_order']
        verbose_name = _('Social link')
        verbose_name_plural = _('Social links')

    def __str__(self):
        return self.get_platform_display()


class FeedbackCTA(models.Model):
    """Singleton model for shared feedback CTA block"""

    title = models.TextField(
        _('Feedback title'),
        default='',
        help_text=_('HTML allowed'),
    )
    cta_text = models.CharField(
        _('Button text'),
        max_length=100,
        default='',
    )

    class Meta:
        verbose_name = _('Feedback CTA')
        verbose_name_plural = _('Feedback CTA')

    def __str__(self):
        return 'Feedback CTA'

    def save(self, *args, **kwargs):
        if not self.pk and FeedbackCTA.objects.exists():
            raise ValueError('Only one FeedbackCTA instance is allowed.')
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'title': (
                    'Not sure which plan to choose? Submit a request '
                    '<span class="md:block">and our manager will help you choose.</span>'
                ),
                'cta_text': 'Submit a request',
            }
        )
        return obj
