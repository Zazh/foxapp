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

        # Количество машин
        try:
            quantity = max(1, int(request.POST.get('quantity', 1)))
        except (ValueError, TypeError):
            quantity = 1

        # Валидация — period обязателен
        if not period_id:
            from django.contrib import messages
            messages.error(request, 'Please select a rental period.')
            return redirect('tariff_detail', service_type=service_type, slug=slug)

        # Валидация периода
        period = get_object_or_404(TariffPeriod, id=period_id, tariff=tariff, is_active=True)

        # Валидация обязательных политик (только ещё не принятые)
        from policies.models import Policy, PolicyConsent
        required_policies = Policy.objects.filter(is_active=True, is_required=True)
        already_accepted_ids = set(
            PolicyConsent.objects.filter(user=request.user)
            .values_list('policy_id', flat=True)
        )
        unaccepted_policies = required_policies.exclude(id__in=already_accepted_ids)
        if unaccepted_policies.exists():
            accepted_ids = set(request.POST.getlist('accepted_policies'))
            required_ids = set(str(p.id) for p in unaccepted_policies)
            if not required_ids.issubset(accepted_ids):
                from django.contrib import messages
                messages.error(request, 'You must accept all required policies.')
                return redirect('tariff_detail', service_type=service_type, slug=slug)

        # Проверить доступность мест (для N машин)
        if tariff.available_units < quantity:
            return render(request, 'bookings/no_availability.html', {
                'tariff': tariff,
                'service': service,
            })

        # Рассчитать цены с учётом тиров
        unit_price_aed = period.get_unit_price(quantity)
        price_aed = unit_price_aed * quantity
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

        # Дата начала
        start_date = timezone.now().date()

        # Создать бронирование
        booking = Booking.objects.create(
            user=request.user,
            tariff=tariff,
            period=period,
            start_date=start_date,
            quantity=quantity,
            unit_price_aed=unit_price_aed,
            price_aed=price_aed,
            addons_aed=addons_aed,
            deposit_aed=deposit_aed,
            total_aed=total_aed,
        )

        # Записать согласие с политиками
        if unaccepted_policies.exists():
            for policy in unaccepted_policies:
                PolicyConsent.objects.update_or_create(
                    user=request.user,
                    policy=policy,
                    defaults={'ip_address': request.META.get('REMOTE_ADDR')}
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
                            'name': f"{tariff.name} — {period.name}" + (f" x{quantity}" if quantity > 1 else ""),
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


class BookingCheckoutView(LoginRequiredMixin, View):
    """Повторная оплата pending бронирования через Stripe"""

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user, status=Booking.Status.PENDING)

        # Бронирование истекло
        if booking.expires_at < timezone.now():
            booking.cancel()
            return render(request, 'bookings/cancelled.html', {
                'booking': booking,
                'expired': True,
            })

        # Если Stripe не настроен — mock режим
        if not is_stripe_configured():
            return redirect('booking_mock_payment', pk=booking.pk)

        # Создать новую Stripe Checkout Session
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'aed',
                        'unit_amount': int(booking.total_aed * 100),
                        'product_data': {
                            'name': f"{booking.tariff.name} — {booking.period.name}" + (
                                f" x{booking.quantity}" if booking.quantity > 1 else ""
                            ),
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
                metadata={'booking_id': booking.pk},
            )

            booking.stripe_session_id = checkout_session.id
            booking.save(update_fields=['stripe_session_id'])

            return redirect(checkout_session.url)

        except stripe.error.StripeError as e:
            booking.cancel()
            return render(request, 'bookings/error.html', {
                'error': str(e),
                'tariff': booking.tariff,
            })


class BookingMockPaymentView(LoginRequiredMixin, View):
    """Mock страница оплаты — только при выключенном Stripe"""

    def dispatch(self, request, *args, **kwargs):
        if is_stripe_configured():
            return redirect('cabinet-dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, user=request.user, status=Booking.Status.PENDING)

        if booking.expires_at < timezone.now():
            booking.cancel()
            return render(request, 'bookings/cancelled.html', {
                'booking': booking,
                'expired': True,
            })

        return render(request, 'bookings/mock_payment.html', {
            'booking': booking,
        })

    def post(self, request, pk):
        if is_stripe_configured():
            return redirect('cabinet-dashboard')

        booking = get_object_or_404(Booking, pk=pk, user=request.user, status=Booking.Status.PENDING)

        if booking.expires_at < timezone.now():
            booking.cancel()
            return redirect('booking_cancel', pk=booking.pk)

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