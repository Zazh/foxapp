from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.conf import settings
from django.utils import timezone

from services.models import Service, Tariff, TariffPeriod, AddonService
from .models import Booking, BookingAddon

import stripe


def is_stripe_configured():
    """Проверяет, настроен ли Stripe с реальными ключами"""
    return (
            settings.STRIPE_SECRET_KEY and
            settings.STRIPE_SECRET_KEY.startswith('sk_') and
            len(settings.STRIPE_SECRET_KEY) > 10
    )


class BookingCreateView(LoginRequiredMixin, View):
    """Создание бронирования и редирект на Stripe"""

    def post(self, request, service_type, slug):
        # Получить тариф
        service = get_object_or_404(Service, service_type=service_type, is_active=True)
        tariff = get_object_or_404(Tariff, service=service, slug=slug, is_active=True)

        # Получить данные формы
        period_id = request.POST.get('period')
        addon_ids = request.POST.getlist('addons')

        # Валидация — period обязателен
        if not period_id:
            from django.contrib import messages
            messages.error(request, 'Please select a rental period.')
            return redirect('tariff_detail', service_type=service_type, slug=slug)

        # Валидация периода
        period = get_object_or_404(TariffPeriod, id=period_id, tariff=tariff, is_active=True)

        # Проверить доступность мест
        if tariff.available_units == 0:
            return render(request, 'bookings/no_availability.html', {
                'tariff': tariff,
                'service': service,
            })

        # Рассчитать цены
        price_aed = period.price_aed
        deposit_aed = tariff.deposit_aed

        # Аддоны
        addons_aed = 0
        selected_addons = []
        if addon_ids:
            addons = AddonService.objects.filter(id__in=addon_ids, service=service, is_active=True)
            for addon in addons:
                addons_aed += addon.price_aed
                selected_addons.append(addon)

        total_aed = price_aed + addons_aed + deposit_aed

        # Дата начала (если не указана — завтра)
        start_date = timezone.now().date()

        # Создать бронирование
        booking = Booking.objects.create(
            user=request.user,
            tariff=tariff,
            period=period,
            start_date=start_date,
            price_aed=price_aed,
            addons_aed=addons_aed,
            deposit_aed=deposit_aed,
            total_aed=total_aed,
        )

        # Сохранить аддоны
        for addon in selected_addons:
            BookingAddon.objects.create(
                booking=booking,
                addon=addon,
                price_aed=addon.price_aed
            )

        # Если Stripe не настроен — mock режим
        if not is_stripe_configured():
            return redirect('booking_mock_payment', pk=booking.pk)

        # Создать Stripe Checkout Session
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'aed',
                        'unit_amount': int(total_aed * 100),
                        'product_data': {
                            'name': f"{tariff.name} — {period.name}",
                            'description': f"Deposit: {deposit_aed} AED",
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=request.build_absolute_uri(
                    reverse('booking_success', args=[booking.pk])
                ) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=request.build_absolute_uri(
                    reverse('booking_cancel', args=[booking.pk])
                ),
                client_reference_id=str(booking.pk),
                customer_email=request.user.email,
                metadata={
                    'booking_id': booking.pk,
                },
            )

            booking.stripe_session_id = checkout_session.id
            booking.save(update_fields=['stripe_session_id'])

            return redirect(checkout_session.url)

        except stripe.error.StripeError as e:
            booking.cancel()
            return render(request, 'bookings/error.html', {
                'error': str(e),
                'tariff': tariff,
            })


class BookingMockPaymentView(LoginRequiredMixin, View):
    """Mock страница оплаты для тестирования"""

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user, status=Booking.Status.PENDING)

        return render(request, 'bookings/mock_payment.html', {
            'booking': booking,
        })

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user, status=Booking.Status.PENDING)

        action = request.POST.get('action')

        if action == 'pay':
            booking.mark_as_paid('mock_payment_' + str(booking.pk))
            return redirect('booking_success', pk=booking.pk)
        else:
            booking.cancel()
            return redirect('booking_cancel', pk=booking.pk)


class BookingSuccessView(LoginRequiredMixin, View):
    """Страница успешной оплаты"""

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user)

        # Проверить оплату через Stripe (если webhook ещё не сработал)
        if booking.status == Booking.Status.PENDING and is_stripe_configured():
            stripe.api_key = settings.STRIPE_SECRET_KEY
            session_id = request.GET.get('session_id')

            if session_id:
                try:
                    session = stripe.checkout.Session.retrieve(session_id)
                    if session.payment_status == 'paid':
                        booking.mark_as_paid(session.payment_intent)
                except stripe.error.StripeError:
                    pass

        return render(request, 'bookings/success.html', {
            'booking': booking,
        })


class BookingCancelView(LoginRequiredMixin, View):
    """Отмена бронирования"""

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user)

        if booking.status == Booking.Status.PENDING:
            booking.cancel()

        return render(request, 'bookings/cancelled.html', {
            'booking': booking,
        })


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(View):
    """Webhook от Stripe"""

    def post(self, request):
        if not is_stripe_configured():
            return JsonResponse({'status': 'stripe not configured'})

        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return HttpResponseBadRequest('Invalid payload')
        except stripe.error.SignatureVerificationError:
            return HttpResponseBadRequest('Invalid signature')

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            booking_id = session.get('client_reference_id')

            if booking_id:
                try:
                    booking = Booking.objects.get(pk=booking_id)
                    if booking.status == Booking.Status.PENDING:
                        booking.mark_as_paid(session.get('payment_intent', ''))
                except Booking.DoesNotExist:
                    pass

        return JsonResponse({'status': 'ok'})