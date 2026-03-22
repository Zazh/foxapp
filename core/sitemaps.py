from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from services.models import Service, Tariff
from policies.models import Policy


class StaticSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 1.0
    i18n = True

    def items(self):
        return ['home', 'about', 'contacts']

    def location(self, item):
        return reverse(item)


class ServiceSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8
    i18n = True

    def items(self):
        return Service.objects.filter(is_active=True)

    def location(self, obj):
        return reverse('service_detail', kwargs={'service_type': obj.service_type})


class TariffSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.9
    i18n = True

    def items(self):
        return Tariff.objects.filter(is_active=True, is_custom=False).select_related('service')

    def location(self, obj):
        return reverse('tariff_detail', kwargs={
            'service_type': obj.service.service_type,
            'slug': obj.slug,
        })

    def lastmod(self, obj):
        return obj.updated_at


class PolicySitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.4
    i18n = True

    def items(self):
        return Policy.objects.filter(is_active=True)

    def location(self, obj):
        return reverse('policy_detail', kwargs={'slug': obj.slug})

    def lastmod(self, obj):
        return obj.updated_at
