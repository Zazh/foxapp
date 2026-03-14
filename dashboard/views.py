from django.http import JsonResponse
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone

from bookings.models import Booking


class DashboardMixin(LoginRequiredMixin):
    """Базовый миксин для всех страниц кабинета"""
    pass


class DashboardHomeView(DashboardMixin, TemplateView):
    """Главная страница кабинета — активные бронирования"""
    template_name = 'cabinet/dashboard/cabinet.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Только основные бронирования (не продления)
        active_bookings = list(Booking.objects.filter(
            user=user,
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
            parent_booking__isnull=True,
            storage_unit__isnull=False,
        ).select_related(
            'tariff', 'tariff__location', 'tariff__service',
            'storage_unit', 'storage_unit__section',
        ).order_by('-end_date'))

        # Pending бронирования (ожидают оплаты, ещё не истекли)
        pending_bookings = Booking.objects.filter(
            user=user,
            status=Booking.Status.PENDING,
            expires_at__gt=now,
        ).order_by('-created_at')[:5]

        context['active_bookings'] = active_bookings
        context['pending_bookings'] = pending_bookings
        context['has_active'] = len(active_bookings) > 0

        # Onboarding: show modal if profile is incomplete
        user = self.request.user
        context['show_onboarding'] = not user.telegram_id or not user.phone or not user.id_card

        return context


class DashboardHistoryView(DashboardMixin, TemplateView):
    """История посещений"""
    template_name = 'cabinet/dashboard/history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        from visits.models import Visit

        # Все посещения пользователя (снепшот-данные в самой модели)
        visits = Visit.objects.filter(
            booking__user=user
        ).order_by('-visited_at')

        context['visits'] = visits

        return context

class DashboardBillingView(DashboardMixin, TemplateView):
    """Billing — платежи и ожидающие оплаты"""
    template_name = 'cabinet/dashboard/billing.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Оплаченные бронирования
        context['paid_bookings'] = Booking.objects.filter(
            user=user,
            paid_at__isnull=False,
        ).select_related('tariff', 'period').order_by('-paid_at')

        # Pending (ожидают оплаты, ещё не истекли)
        context['pending_payments'] = Booking.objects.filter(
            user=user,
            status=Booking.Status.PENDING,
            expires_at__gt=now,
        ).select_related('tariff', 'period').order_by('-created_at')

        return context


class BookingDetailView(DashboardMixin, TemplateView):
    """Детали бронирования + управление"""
    template_name = 'cabinet/dashboard/manage.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking_id = kwargs.get('pk')

        booking = get_object_or_404(
            Booking.objects.select_related(
                'tariff', 'tariff__location', 'tariff__service',
                'period', 'storage_unit', 'storage_unit__section'
            ).prefetch_related('booking_addons__addon'),  # Исправлено
            pk=booking_id,
            user=self.request.user
        )

        # Периоды для продления (того же тарифа)
        periods = booking.tariff.periods.filter(is_active=True).order_by('duration_value')

        # Аддоны
        addons = booking.tariff.service.addons.filter(is_active=True)

        context['booking'] = booking
        context['periods'] = periods
        context['addons'] = addons

        return context


class ExtendBookingView(DashboardMixin, View):
    """Продление бронирования"""

    def post(self, request, pk):
        from services.models import TariffPeriod, AddonService

        booking = get_object_or_404(
            Booking,
            pk=pk,
            user=request.user,
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE]
        )

        period_id = request.POST.get('period')
        addon_ids = request.POST.getlist('addons')

        if not period_id:
            messages.error(request, _('Please select a period.'))
            return redirect('cabinet-booking-detail', pk=pk)

        period = get_object_or_404(
            TariffPeriod,
            id=period_id,
            tariff=booking.tariff,
            is_active=True
        )

        # Рассчитать цены (продление — всегда 1 юнит)
        price_aed = period.get_unit_price(1)
        addons_aed = 0
        selected_addons = []

        if addon_ids:
            addons = AddonService.objects.filter(
                id__in=addon_ids,
                service=booking.tariff.service,
                is_active=True
            )
            for addon in addons:
                addons_aed += addon.price_aed
                selected_addons.append(addon)

        total_aed = price_aed + addons_aed  # Без депозита при продлении

        # Новая дата начала = текущая дата окончания
        new_start_date = booking.end_date

        # Создать новое бронирование (продление)
        from bookings.models import BookingAddon

        extension = Booking.objects.create(
            user=request.user,
            tariff=booking.tariff,
            period=period,
            storage_unit=booking.storage_unit,  # Тот же unit
            start_date=new_start_date,
            price_aed=price_aed,
            addons_aed=addons_aed,
            deposit_aed=0,  # Депозит уже оплачен
            total_aed=total_aed,
            parent_booking=booking,  # Связь с родительским бронированием
        )

        # Сохранить аддоны
        for addon in selected_addons:
            BookingAddon.objects.create(
                booking=extension,
                addon=addon,
                price_aed=addon.price_aed
            )

        # Редирект на оплату (checkout сам решит: Stripe или mock)
        return redirect('booking_checkout', pk=extension.pk)


class DashboardSettingsView(DashboardMixin, TemplateView):
    """Настройки профиля"""
    template_name = 'cabinet/dashboard/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context

    def post(self, request):
        """Сохранение профиля"""
        user = request.user

        user.first_name = request.POST.get('first_name', '').strip()
        user.middle_name = request.POST.get('middle_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.phone = request.POST.get('phone', '').strip()
        user.id_card = request.POST.get('id_card', '').strip()

        user.save(update_fields=['first_name', 'middle_name', 'last_name', 'phone', 'id_card'])

        messages.success(request, _('Profile updated successfully.'))
        return redirect('cabinet-settings')


class ChangePasswordView(DashboardMixin, View):
    """Смена пароля (AJAX)"""

    def post(self, request):
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # Валидация
        if not current_password or not new_password or not confirm_password:
            return JsonResponse({
                'success': False,
                'error': _('All fields are required.')
            }, status=400)

        if not request.user.check_password(current_password):
            return JsonResponse({
                'success': False,
                'error': _('Current password is incorrect.')
            }, status=400)

        if new_password != confirm_password:
            return JsonResponse({
                'success': False,
                'error': _('Passwords do not match.')
            }, status=400)

        if len(new_password) < 8:
            return JsonResponse({
                'success': False,
                'error': _('Password must be at least 8 characters.')
            }, status=400)

        # Сменить пароль
        request.user.set_password(new_password)
        request.user.save()

        # Обновить сессию чтобы не разлогинило
        update_session_auth_hash(request, request.user)

        return JsonResponse({
            'success': True,
            'message': _('Password changed successfully.')
        })


class DeactivateAccountView(DashboardMixin, View):
    """Деактивация аккаунта"""

    def post(self, request):
        user = request.user

        # Деактивировать, не удалять
        user.is_active = False
        user.save(update_fields=['is_active'])

        # Разлогинить
        from django.contrib.auth import logout
        logout(request)

        return JsonResponse({
            'success': True,
            'redirect': '/'
        })