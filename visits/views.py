import secrets
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

from .models import AccessToken, Visit
from bookings.models import Booking


class GenerateQRTokenView(LoginRequiredMixin, View):
    """Генерация или получение существующего QR токена для владельца"""

    def post(self, request):
        booking_id = request.POST.get('booking_id')

        booking = get_object_or_404(
            Booking,
            pk=booking_id,
            user=request.user,
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE]
        )

        if not booking.storage_unit:
            return JsonResponse({
                'success': False,
                'error': _('No storage unit assigned.')
            }, status=400)

        # Поискать существующий валидный токен
        existing_token = AccessToken.objects.filter(
            booking=booking,
            token_type=AccessToken.TokenType.OWNER,
            expires_at__gt=timezone.now()
        ).first()

        if existing_token:
            token = existing_token
            # Рассчитать оставшееся время в минутах
            remaining = (token.expires_at - timezone.now()).total_seconds() / 60
            expires_in = max(1, int(remaining))
        else:
            # Создать новый токен
            token = AccessToken.objects.create(
                booking=booking,
                token_type=AccessToken.TokenType.OWNER
            )
            expires_in = 15

        return JsonResponse({
            'success': True,
            'token': token.token,
            'unit_number': booking.storage_unit.unit_number,
            'full_code': booking.storage_unit.full_code,
            'expires_in': expires_in,
            'expires_at': token.expires_at.isoformat(),
            'is_new': not existing_token
        })


class GenerateGuestTokenView(LoginRequiredMixin, View):
    """Генерация или получение существующего гостевого QR токена"""

    def post(self, request):
        booking_id = request.POST.get('booking_id')

        booking = get_object_or_404(
            Booking,
            pk=booking_id,
            user=request.user,
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE]
        )

        if not booking.storage_unit:
            return JsonResponse({
                'success': False,
                'error': _('No storage unit assigned.')
            }, status=400)

        # Поискать существующий валидный неиспользованный гостевой токен
        existing_token = AccessToken.objects.filter(
            booking=booking,
            token_type=AccessToken.TokenType.GUEST,
            expires_at__gt=timezone.now(),
            is_used=False
        ).first()

        if existing_token:
            token = existing_token
            remaining = (token.expires_at - timezone.now()).total_seconds() / 3600
            expires_in = max(1, int(remaining))
        else:
            # Создать гостевой токен (без имени — его введёт менеджер)
            token = AccessToken.objects.create(
                booking=booking,
                token_type=AccessToken.TokenType.GUEST
            )
            expires_in = 24

        # Ссылка для гостя
        guest_link = request.build_absolute_uri(f'/visit/guest/{token.token}/')

        return JsonResponse({
            'success': True,
            'token': token.token,
            'unit_number': booking.storage_unit.unit_number,
            'full_code': booking.storage_unit.full_code,
            'guest_link': guest_link,
            'expires_in': expires_in,
            'expires_at': token.expires_at.isoformat(),
            'is_new': not existing_token
        })


class ScanQRView(View):
    """Сканирование QR менеджером (staff only)"""

    def post(self, request):
        # Проверка что это staff
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({
                'success': False,
                'error': _('Access denied.')
            }, status=403)

        token_value = request.POST.get('token', '').strip()
        guest_name = request.POST.get('guest_name', '').strip()

        if not token_value:
            return JsonResponse({
                'success': False,
                'error': _('Token is required.')
            }, status=400)

        # Найти токен
        try:
            token = AccessToken.objects.select_related(
                'booking', 'booking__user', 'booking__storage_unit'
            ).get(token=token_value)
        except AccessToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': _('Invalid token.')
            }, status=404)

        # Проверить валидность
        if token.is_expired:
            return JsonResponse({
                'success': False,
                'error': _('Token has expired.')
            }, status=400)

        if token.is_used and token.token_type == AccessToken.TokenType.GUEST:
            return JsonResponse({
                'success': False,
                'error': _('Guest token has already been used.')
            }, status=400)

        # Для гостевого токена требуем имя гостя
        if token.token_type == AccessToken.TokenType.GUEST:
            if not guest_name:
                return JsonResponse({
                    'success': False,
                    'error': _('Guest name is required.'),
                    'require_guest_name': True,
                    'unit': token.booking.storage_unit.full_code if token.booking.storage_unit else ''
                }, status=400)

            # Сохранить имя гостя в токен
            token.guest_name = guest_name
            token.save(update_fields=['guest_name'])



        # Определить имя посетителя
        if token.token_type == AccessToken.TokenType.OWNER:
            visitor_name = token.booking.user.get_full_name()
        else:
            visitor_name = guest_name

        # Создать запись посещения
        visit = Visit.objects.create(
            booking=token.booking,
            access_token=token,
            visitor_type=token.token_type,
            visitor_name=visitor_name,
            scanned_by=request.user
        )

        # Отметить гостевой токен как использованный
        if token.token_type == AccessToken.TokenType.GUEST:
            token.mark_as_used()


        # Отправить уведомление владельцу
        try:
            from notifications.services import notify_visit
            notify_visit(visit)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Notification error: {e}")


        return JsonResponse({
            'success': True,
            'message': _('Access granted.'),
            'visit': {
                'id': visit.id,
                'unit': token.booking.storage_unit.full_code if token.booking.storage_unit else '',
                'visitor_type': visit.visitor_type,
                'visitor_name': visit.visitor_name,
                'owner_name': token.booking.user.get_full_name(),
                'owner_email': token.booking.user.email,
                'visited_at': visit.visited_at.isoformat()
            }
        })


class VisitHistoryView(LoginRequiredMixin, View):
    """История посещений пользователя (API)"""

    def get(self, request):
        booking_id = request.GET.get('booking_id')

        visits_qs = Visit.objects.filter(
            booking__user=request.user
        ).select_related('booking__storage_unit')

        if booking_id:
            visits_qs = visits_qs.filter(booking_id=booking_id)

        visits = []
        for visit in visits_qs[:50]:
            visits.append({
                'id': visit.id,
                'unit': visit.booking.storage_unit.full_code if visit.booking.storage_unit else '',
                'visitor_type': visit.visitor_type,
                'visitor_name': visit.visitor_name,
                'visited_at': visit.visited_at.isoformat()
            })

        return JsonResponse({
            'success': True,
            'visits': visits
        })


@method_decorator(staff_member_required, name='dispatch')
class ScanPageView(TemplateView):
    """Страница сканирования QR для менеджеров"""
    template_name = 'visits/scan.html'