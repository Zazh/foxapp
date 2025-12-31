from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from .models import Service, Tariff


class ServiceDetailView(View):
    """Страница услуги — редирект если 1 тариф, иначе список"""

    def get(self, request, service_type):
        service = get_object_or_404(Service, service_type=service_type, is_active=True)
        tariffs = Tariff.objects.filter(
            service=service,
            is_active=True,
            is_custom=False
        ).select_related('location')

        # Если 1 тариф — редирект на него
        if tariffs.count() == 1:
            tariff = tariffs.first()
            return redirect('tariff_detail', service_type=service_type, slug=tariff.slug)

        # Несколько тарифов — показать список
        return render(request, 'public/content/services.html', {
            'service': service,
            'tariffs': tariffs,
        })


class TariffDetailView(View):
    """Детальная страница тарифа"""

    def get(self, request, service_type, slug):
        service = get_object_or_404(Service, service_type=service_type, is_active=True)
        tariff = get_object_or_404(
            Tariff.objects.select_related('service', 'location').prefetch_related(
                'sizes', 'periods', 'benefits', 'images'
            ),
            service=service,
            slug=slug,
            is_active=True,
            is_custom=False
        )

        # Активные периоды (не кастомные)
        periods = tariff.periods.filter(is_active=True, is_custom=False)

        # Доп. услуги
        addons = service.addons.filter(is_active=True)

        return render(request, 'public/content/tariff_detail.html', {
            'service': service,
            'tariff': tariff,
            'periods': periods,
            'addons': addons,
        })