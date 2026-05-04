from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, ListView, DetailView
from django.db.models import Count, Q, Case, When, Value, IntegerField, Subquery, OuterRef, CharField, Min, Sum
from django.db.models.functions import TruncDate
import json
from django.utils import timezone
from django.http import JsonResponse
from django.contrib import messages
from datetime import timedelta

from bookings.models import Booking
from accounts.models import User
from visits.models import Visit
from feedback.models import FeedbackRequest
from services.models import StorageUnit, Section
from locations.models import Location




@method_decorator(staff_member_required, name='dispatch')
class DashboardView(TemplateView):
    """Главная страница backoffice"""
    template_name = 'backoffice/dashboard.html'

    STORAGE_LOCATION_TYPES = [
        Location.LocationType.AUTO_STORAGE,
        Location.LocationType.STORAGE,
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Статистика бронирований
        context['stats'] = {
            'active_bookings': Booking.objects.filter(
                status=Booking.Status.PAID,
                parent_booking__isnull=True,
            ).count(),
            'pending_bookings': Booking.objects.filter(
                status=Booking.Status.PENDING,
                expires_at__gt=timezone.now(),
            ).count(),
            'today_visits': Visit.objects.filter(
                visited_at__date=today
            ).count(),
            'new_feedback': FeedbackRequest.objects.filter(
                status=FeedbackRequest.Status.NEW
            ).count(),
            'expired_unreleased': Booking.overdue_qs(today).count(),
            'expiring_soon': Booking.objects.filter(
                status=Booking.Status.PAID,
                parent_booking__isnull=True,
                end_date__lte=today + timedelta(days=7),
                end_date__gte=today
            ).count(),
        }

        # Статистика юнитов для donut chart
        storage_qs = StorageUnit.objects.filter(
            section__location__location_type__in=self.STORAGE_LOCATION_TYPES,
            is_active=True,
        )
        total_units = storage_qs.count()
        expired_units = storage_qs.filter(
            is_available=False,
            bookings__status=Booking.Status.PAID,
            bookings__parent_booking__isnull=True,
            bookings__end_date__lt=today,
        ).distinct().count()
        expiring_units = storage_qs.filter(
            is_available=False,
            bookings__status=Booking.Status.PAID,
            bookings__parent_booking__isnull=True,
            bookings__end_date__gte=today,
            bookings__end_date__lte=today + timedelta(days=14),
        ).distinct().count()
        occupied_units = storage_qs.filter(
            is_available=False,
        ).distinct().count()
        # "occupied" в чистом виде = occupied - expired - expiring
        occupied_normal = max(0, occupied_units - expired_units - expiring_units)
        available_units = total_units - occupied_units

        context['unit_stats'] = {
            'total': total_units,
            'available': available_units,
            'occupied': occupied_normal,
            'expiring': expiring_units,
            'expired': expired_units,
        }

        # Визиты за 7 дней (для bar chart)
        week_ago = today - timedelta(days=6)
        visits_by_day = dict(
            Visit.objects.filter(
                visited_at__date__gte=week_ago,
            ).annotate(
                day=TruncDate('visited_at')
            ).values('day').annotate(
                total=Count('id'),
                owners=Count('id', filter=Q(visitor_type=Visit.VisitorType.OWNER)),
                guests=Count('id', filter=Q(visitor_type=Visit.VisitorType.GUEST)),
            ).values_list('day', 'total')
        )
        # Build 7-day array with all days filled
        visit_chart = []
        for i in range(7):
            d = week_ago + timedelta(days=i)
            visit_chart.append({
                'date': d.strftime('%a'),
                'date_full': d.strftime('%d %b'),
                'count': visits_by_day.get(d, 0),
                'is_today': d == today,
            })
        context['visit_chart'] = visit_chart
        context['visit_chart_json'] = json.dumps(visit_chart)
        context['visit_week_total'] = sum(v['count'] for v in visit_chart)

        # Последние заявки
        context['recent_feedback'] = FeedbackRequest.objects.filter(
            status=FeedbackRequest.Status.NEW
        ).select_related('user').order_by('-created_at')[:5]

        # Expired (unreleased) — требуют внимания менеджера
        context['expired_bookings'] = Booking.overdue_qs(today).select_related(
            'user'
        ).order_by('end_date')

        # Expiring soon (14 дней)
        context['expiring_bookings'] = Booking.objects.filter(
            status=Booking.Status.PAID,
            parent_booking__isnull=True,
            end_date__gte=today,
            end_date__lte=today + timedelta(days=14),
        ).select_related('user').order_by('end_date')

        # Последние бронирования
        context['recent_bookings'] = Booking.objects.select_related(
            'user'
        ).order_by('-created_at')[:5]

        # Сегодняшние посещения
        context['today_visits_list'] = Visit.objects.filter(
            visited_at__date=today
        ).order_by('-visited_at')[:10]

        return context


@method_decorator(staff_member_required, name='dispatch')
class BookingListView(ListView):
    """Список активных бронирований — оперативное управление арендой"""
    model = Booking
    template_name = 'backoffice/bookings/list.html'
    context_object_name = 'bookings'
    paginate_by = 20

    def get_queryset(self):
        today = timezone.now().date()

        status = self.request.GET.get('status')

        if status == 'expired':
            # Просрочено — PAID + end_date в прошлом
            qs = Booking.overdue_qs(today).order_by('end_date')
        elif status == 'expiring_soon':
            qs = Booking.objects.filter(
                status=Booking.Status.PAID,
                parent_booking__isnull=True,
                end_date__gte=today,
                end_date__lte=today + timedelta(days=14),
            ).order_by('end_date')
        elif status == 'active':
            # В работе сейчас — PAID + start_date наступил + end_date ещё не прошёл
            qs = Booking.active_qs(today).order_by('end_date')
        else:
            # По умолчанию: всё PAID + parent_booking__isnull, с приоритетной
            # сортировкой (overdue → expiring_soon → expiring_2w → rest)
            qs = Booking.objects.filter(
                status=Booking.Status.PAID,
                parent_booking__isnull=True,
            ).annotate(
                sort_priority=Case(
                    When(end_date__lt=today, then=Value(0)),  # overdue
                    When(end_date__lte=today + timedelta(days=7), then=Value(1)),
                    When(end_date__lte=today + timedelta(days=14), then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
            ).order_by('sort_priority', 'end_date')

        qs = qs.select_related('user', 'tariff', 'tariff__location', 'period', 'storage_unit')

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(tariff_name__icontains=search) |
                Q(unit_codes__icontains=search) |
                Q(location_name__icontains=search) |
                Q(pk__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')

        # Счётчики для фильтров (всё считается из PAID-брони, разница в датах)
        base = Booking.objects.filter(
            status=Booking.Status.PAID, parent_booking__isnull=True,
        )
        context['stats'] = {
            'active': base.filter(
                start_date__lte=today, end_date__gte=today,
            ).count(),
            'expired': base.filter(end_date__lt=today).count(),
            'expiring_soon': base.filter(
                end_date__gte=today,
                end_date__lte=today + timedelta(days=14),
            ).count(),
        }

        return context


@method_decorator(staff_member_required, name='dispatch')
class BookingDetailView(DetailView):
    """Детали бронирования"""
    model = Booking
    template_name = 'backoffice/bookings/detail.html'
    context_object_name = 'booking'

    def get_queryset(self):
        return Booking.objects.select_related(
            'user', 'tariff', 'storage_unit', 'tariff__location', 'period'
        ).prefetch_related('booking_addons__addon', 'extensions')


@method_decorator(staff_member_required, name='dispatch')
class PaymentListView(ListView):
    """Платежи — фокус на финансовой стороне бронирований"""
    model = Booking
    template_name = 'backoffice/payments/list.html'
    context_object_name = 'payments'
    paginate_by = 20

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'user', 'tariff', 'tariff__location', 'period', 'storage_unit'
        ).order_by('-created_at')

        # Фильтр по статусу оплаты
        payment_status = self.request.GET.get('status')
        if payment_status == 'paid':
            qs = qs.filter(paid_at__isnull=False).order_by('-paid_at')
        elif payment_status == 'pending':
            qs = qs.filter(
                status=Booking.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
        elif payment_status == 'failed':
            qs = qs.filter(
                status=Booking.Status.CANCELLED,
                paid_at__isnull=True,
            )

        # Фильтр по способу оплаты
        method = self.request.GET.get('method')
        if method in dict(Booking.PaymentMethod.choices):
            qs = qs.filter(payment_method=method)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(stripe_payment_id__icontains=search) |
                Q(stripe_session_id__icontains=search) |
                Q(pk__icontains=search) |
                Q(number__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['current_status'] = self.request.GET.get('status', '')
        context['current_method'] = self.request.GET.get('method', '')
        context['search'] = self.request.GET.get('search', '')
        context['payment_methods'] = Booking.PaymentMethod.choices

        # Статистика по способам оплаты — выручка для каждого канала
        paid_qs = Booking.objects.filter(paid_at__isnull=False)
        revenue_by_method = dict(
            paid_qs.values_list('payment_method').annotate(
                total=Sum('payment_amount_collected'),
            )
        )

        context['stats'] = {
            'total_paid': paid_qs.count(),
            'total_revenue': paid_qs.aggregate(
                total=Sum('payment_amount_collected'),
            )['total'] or 0,
            'pending': Booking.objects.filter(
                status=Booking.Status.PENDING,
                expires_at__gt=now,
            ).count(),
            'failed': Booking.objects.filter(
                status=Booking.Status.CANCELLED,
                paid_at__isnull=True,
            ).count(),
            'revenue_online': revenue_by_method.get('lk_invoice') or 0,
            'revenue_cash': revenue_by_method.get('cash') or 0,
            'revenue_link': revenue_by_method.get('stripe_payment_link') or 0,
        }

        return context


@method_decorator(staff_member_required, name='dispatch')
class UserListView(ListView):
    """Список пользователей"""
    model = User
    template_name = 'backoffice/users/list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.annotate(
            bookings_count=Count('bookings')
        ).order_by('-date_joined')

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


@method_decorator(staff_member_required, name='dispatch')
class UserDetailView(DetailView):
    """Детали пользователя"""
    model = User
    template_name = 'backoffice/users/detail.html'
    context_object_name = 'profile_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bookings'] = self.object.bookings.select_related(
            'tariff', 'tariff__location', 'period', 'storage_unit'
        ).order_by('-created_at')[:10]
        return context


@staff_member_required
def user_set_password(request, pk):
    """Менеджер задаёт новый пароль клиента (например, восстановление доступа)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    target = get_object_or_404(User, pk=pk)

    # Защита от эскалации привилегий: рядовой staff не может перебить пароль
    # суперюзера. Сам суперюзер — может (через Django admin это и так возможно).
    if target.is_superuser and not request.user.is_superuser:
        return JsonResponse(
            {'success': False, 'error': 'Cannot change a superuser password.'},
            status=403,
        )

    new_password = (request.POST.get('password') or '').strip()
    if not new_password:
        return JsonResponse(
            {'success': False, 'error': 'Password is required.'}, status=400,
        )

    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    try:
        validate_password(new_password, target)
    except ValidationError as e:
        return JsonResponse(
            {'success': False, 'error': ' '.join(e.messages)}, status=400,
        )

    target.set_password(new_password)
    target.save(update_fields=['password'])

    return JsonResponse({
        'success': True,
        'message': f'Password updated for {target.email}.',
    })


@staff_member_required
def user_update(request, pk):
    """Редактирование данных пользователя менеджером."""
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    user = get_object_or_404(User, pk=pk)

    user.first_name = request.POST.get('first_name', '').strip()
    user.middle_name = request.POST.get('middle_name', '').strip()
    user.last_name = request.POST.get('last_name', '').strip()
    user.phone = request.POST.get('phone', '').strip()
    user.id_card = request.POST.get('id_card', '').strip()
    user.email = request.POST.get('email', '').strip() or user.email

    user.save(update_fields=[
        'first_name', 'middle_name', 'last_name',
        'phone', 'id_card', 'email',
    ])

    messages.success(request, f'User {user.email} updated.')
    return redirect('backoffice:user_detail', pk=pk)


@method_decorator(staff_member_required, name='dispatch')
class VisitListView(ListView):
    """История посещений"""
    model = Visit
    template_name = 'backoffice/visits/list.html'
    context_object_name = 'visits'
    paginate_by = 20

    def _get_date_range(self):
        """Parse date_from / date_to from GET. Returns (date|None, date|None)."""
        from datetime import date as dt_date
        today = timezone.now().date()
        date_from_raw = self.request.GET.get('date_from')
        date_to_raw = self.request.GET.get('date_to')
        date_from = None
        date_to = None
        try:
            if date_from_raw:
                date_from = dt_date.fromisoformat(date_from_raw)
        except (ValueError, TypeError):
            pass
        try:
            if date_to_raw:
                date_to = dt_date.fromisoformat(date_to_raw)
        except (ValueError, TypeError):
            pass
        return date_from, date_to

    def _get_chart_range(self):
        """Range for chart/stats: explicit dates or last 30 days."""
        today = timezone.now().date()
        date_from, date_to = self._get_date_range()
        return date_from or (today - timedelta(days=29)), date_to or today

    def get_queryset(self):
        qs = Visit.objects.select_related(
            'booking__user', 'booking__storage_unit__section__location'
        ).order_by('-visited_at')

        date_from, date_to = self._get_date_range()
        if date_from:
            qs = qs.filter(visited_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(visited_at__date__lte=date_to)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(booking__user__email__icontains=search) |
                Q(visitor_name__icontains=search) |
                Q(unit_code__icontains=search) |
                Q(location_name__icontains=search) |
                Q(scanned_by_name__icontains=search)
            )

        visitor_type = self.request.GET.get('type')
        if visitor_type:
            qs = qs.filter(visitor_type=visitor_type)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['current_type'] = self.request.GET.get('type', '')

        date_from, date_to = self._get_date_range()
        context['date_from'] = date_from.isoformat() if date_from else ''
        context['date_to'] = date_to.isoformat() if date_to else ''

        # Stats/chart always use a concrete range
        chart_from, chart_to = self._get_chart_range()
        period_qs = Visit.objects.filter(
            visited_at__date__gte=chart_from,
            visited_at__date__lte=chart_to,
        )
        total_days = max((chart_to - chart_from).days + 1, 1)
        total_visits = period_qs.count()
        context['visit_stats'] = {
            'total': total_visits,
            'avg_per_day': round(total_visits / total_days, 1),
            'owners': period_qs.filter(visitor_type=Visit.VisitorType.OWNER).count(),
            'guests': period_qs.filter(visitor_type=Visit.VisitorType.GUEST).count(),
            'days': total_days,
        }

        # Daily chart data
        visits_by_day = dict(
            period_qs.annotate(
                day=TruncDate('visited_at')
            ).values('day').annotate(
                count=Count('id')
            ).values_list('day', 'count')
        )
        today = timezone.now().date()
        chart_data = []
        for i in range(total_days):
            d = chart_from + timedelta(days=i)
            chart_data.append({
                'date': d.strftime('%d'),
                'date_full': d.strftime('%d %b'),
                'weekday': d.strftime('%a'),
                'count': visits_by_day.get(d, 0),
                'is_today': d == today,
            })
        context['visit_chart_json'] = json.dumps(chart_data)

        # Quick period links
        context['quick_periods'] = {
            'week': (today - timedelta(days=6)).isoformat(),
            'month': (today - timedelta(days=29)).isoformat(),
            'quarter': (today - timedelta(days=89)).isoformat(),
        }

        return context


@method_decorator(staff_member_required, name='dispatch')
class FeedbackListView(ListView):
    """Заявки на обратную связь"""
    model = FeedbackRequest
    template_name = 'backoffice/feedback/list.html'
    context_object_name = 'feedbacks'
    paginate_by = 20

    def get_queryset(self):
        qs = FeedbackRequest.objects.order_by('-created_at')

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = FeedbackRequest.Status.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')
        return context


@staff_member_required
def feedback_update_status(request, pk):
    """Обновить статус заявки"""
    if request.method == 'POST':
        feedback = get_object_or_404(FeedbackRequest, pk=pk)
        new_status = request.POST.get('status')

        if new_status in dict(FeedbackRequest.Status.choices):
            feedback.status = new_status
            feedback.save(update_fields=['status', 'updated_at'])

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})

        return redirect('backoffice:feedback_list')

    return JsonResponse({'success': False}, status=400)


@method_decorator(staff_member_required, name='dispatch')
class ScannerView(TemplateView):
    """Страница сканера QR"""
    template_name = 'backoffice/scanner.html'


@staff_member_required
def feedback_update_notes(request, pk):
    """Обновить заметки к заявке"""
    if request.method == 'POST':
        feedback = get_object_or_404(FeedbackRequest, pk=pk)
        notes = request.POST.get('notes', '')

        feedback.manager_notes = notes
        feedback.save(update_fields=['manager_notes', 'updated_at'])

        return JsonResponse({'success': True})

    return JsonResponse({'success': False}, status=400)


@method_decorator(staff_member_required, name='dispatch')
class UnitListView(ListView):
    """Список всех ячеек"""
    model = StorageUnit
    template_name = 'backoffice/units/list.html'
    context_object_name = 'units'
    paginate_by = 50

    # Типы локаций, у которых есть складские юниты
    STORAGE_LOCATION_TYPES = [
        Location.LocationType.AUTO_STORAGE,
        Location.LocationType.STORAGE,
    ]

    def get_queryset(self):
        today = timezone.now().date()

        # Subquery: end_date текущего PAID-бронирования
        current_booking_end = Booking.objects.filter(
            storage_unit=OuterRef('pk'),
            status=Booking.Status.PAID,
            parent_booking__isnull=True,
        ).order_by('-created_at').values('end_date')[:1]

        qs = StorageUnit.objects.filter(
            section__location__location_type__in=self.STORAGE_LOCATION_TYPES,
        ).select_related(
            'section', 'section__location', 'section__service'
        ).annotate(
            booking_end_date=Subquery(current_booking_end),
            sort_priority=Case(
                # Overdue — end_date в прошлом → самый высокий приоритет
                When(
                    is_available=False,
                    booking_end_date__lt=today,
                    then=Value(0),
                ),
                # Expiring <= 7 days
                When(
                    is_available=False,
                    booking_end_date__gte=today,
                    booking_end_date__lte=today + timedelta(days=7),
                    then=Value(1),
                ),
                # Expiring 8-14 days
                When(
                    is_available=False,
                    booking_end_date__gt=today + timedelta(days=7),
                    booking_end_date__lte=today + timedelta(days=14),
                    then=Value(2),
                ),
                default=Value(9),
                output_field=IntegerField(),
            ),
        ).order_by('sort_priority', 'booking_end_date', 'section__location', 'section__sort_order', 'unit_number')

        # Фильтр по локации
        location_id = self.request.GET.get('location')
        if location_id:
            qs = qs.filter(section__location_id=location_id)

        # Фильтр по статусу
        status = self.request.GET.get('status')
        if status == 'available':
            qs = qs.filter(is_available=True, is_active=True)
        elif status == 'occupied':
            qs = qs.filter(is_available=False)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        elif status == 'expiring_soon':
            qs = qs.filter(
                is_available=False,
                bookings__status=Booking.Status.PAID,
                bookings__parent_booking__isnull=True,
                bookings__end_date__gte=today,
                bookings__end_date__lte=today + timedelta(days=14),
            ).distinct()
        elif status == 'expired':
            qs = qs.filter(
                is_available=False,
                bookings__status=Booking.Status.PAID,
                bookings__parent_booking__isnull=True,
                bookings__end_date__lt=today,
            ).distinct()

        # Поиск
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(unit_number__icontains=search)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['locations'] = Location.objects.filter(
            is_active=True,
            location_type__in=self.STORAGE_LOCATION_TYPES,
        )
        context['current_location'] = self.request.GET.get('location', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')

        # Статистика (только складские локации)
        storage_units = StorageUnit.objects.filter(
            section__location__location_type__in=self.STORAGE_LOCATION_TYPES,
        )
        today = timezone.now().date()
        context['stats'] = {
            'total': storage_units.filter(is_active=True).count(),
            'available': storage_units.filter(is_active=True, is_available=True).count(),
            'occupied': storage_units.filter(is_active=True, is_available=False).count(),
            'expiring_soon': storage_units.filter(
                is_available=False,
                bookings__status=Booking.Status.PAID,
                bookings__parent_booking__isnull=True,
                bookings__end_date__gte=today,
                bookings__end_date__lte=today + timedelta(days=14),
            ).distinct().count(),
            'expired': storage_units.filter(
                is_available=False,
                bookings__status=Booking.Status.PAID,
                bookings__parent_booking__isnull=True,
                bookings__end_date__lt=today,
            ).distinct().count(),
        }

        return context


@method_decorator(staff_member_required, name='dispatch')
class UnitDetailView(DetailView):
    """Детали ячейки"""
    model = StorageUnit
    template_name = 'backoffice/units/detail.html'
    context_object_name = 'unit'

    def get_queryset(self):
        return StorageUnit.objects.select_related(
            'section', 'section__location', 'section__service'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Текущее активное бронирование
        context['current_booking'] = Booking.objects.filter(
            storage_unit=self.object,
            status=Booking.Status.PAID,
        ).select_related('user', 'tariff', 'tariff__location', 'period').first()

        # История бронирований
        context['booking_history'] = Booking.objects.filter(
            storage_unit=self.object
        ).select_related('user', 'tariff', 'tariff__location', 'period').order_by('-created_at')[:10]

        # История посещений
        context['recent_visits'] = Visit.objects.filter(
            booking__storage_unit=self.object
        ).select_related('booking__user', 'booking__storage_unit__section__location').order_by('-visited_at')[:10]

        return context


@staff_member_required
def unit_toggle_status(request, pk):
    """Переключить статус ячейки (активна/неактивна)"""
    if request.method == 'POST':
        unit = get_object_or_404(StorageUnit, pk=pk)
        action = request.POST.get('action')

        if action == 'deactivate':
            unit.is_active = False
            unit.save(update_fields=['is_active'])
        elif action == 'activate':
            unit.is_active = True
            unit.save(update_fields=['is_active'])
        elif action == 'release':
            # Освободить ячейку (осторожно!)
            unit.is_available = True
            unit.save(update_fields=['is_available'])

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        return redirect('backoffice:unit_detail', pk=pk)

    return JsonResponse({'success': False}, status=400)


@staff_member_required
def booking_release(request, pk):
    """Освободить ячейку — менеджер подтвердил что машина/вещи забраны"""
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)

        if booking.status != Booking.Status.PAID:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Booking cannot be released'}, status=400)
            return redirect('backoffice:booking_detail', pk=pk)

        booking.complete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        messages.success(request, f'Unit {booking.storage_unit} released successfully')
        return redirect('backoffice:booking_detail', pk=pk)

    return JsonResponse({'success': False}, status=400)


@staff_member_required
def booking_reassign_unit(request, pk):
    """Переселить бронирование на другой юнит."""
    booking = get_object_or_404(
        Booking.objects.select_related('tariff__service', 'tariff__location'),
        pk=pk,
    )

    if booking.status != Booking.Status.PAID:
        messages.error(request, 'Cannot reassign unit for this booking status.')
        return redirect('backoffice:booking_detail', pk=pk)

    # Доступные юниты той же локации/сервиса
    available_units = StorageUnit.objects.filter(
        section__service=booking.tariff.service,
        section__location=booking.tariff.location,
        section__is_active=True,
        is_active=True,
        is_available=True,
    ).select_related('section').order_by('section__sort_order', 'unit_number')

    if request.method == 'POST':
        old_unit_id = request.POST.get('old_unit_id')
        new_unit_id = request.POST.get('new_unit_id')

        if not old_unit_id or not new_unit_id:
            messages.error(request, 'Please select both old and new units.')
            return redirect('backoffice:booking_detail', pk=pk)

        old_unit = get_object_or_404(StorageUnit, pk=old_unit_id)
        new_unit = get_object_or_404(StorageUnit, pk=new_unit_id)

        try:
            booking.reassign_unit(old_unit, new_unit)
            messages.success(
                request,
                f'Unit reassigned: {old_unit.full_code} → {new_unit.full_code}'
            )
        except ValueError as e:
            messages.error(request, str(e))

        return redirect('backoffice:booking_detail', pk=pk)

    # GET — показать форму
    current_units = [
        bu.storage_unit for bu in
        booking.booking_units.select_related('storage_unit__section__location').all()
    ]

    return render(request, 'backoffice/bookings/reassign.html', {
        'booking': booking,
        'current_units': current_units,
        'available_units': available_units,
    })


@staff_member_required
def booking_update_notes(request, pk):
    """Обновить заметки менеджера к бронированию."""
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        booking.manager_notes = request.POST.get('manager_notes', '')
        booking.save(update_fields=['manager_notes', 'updated_at'])

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        next_url = request.POST.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect('backoffice:booking_detail', pk=pk)

    return JsonResponse({'success': False}, status=400)


@staff_member_required
def payment_fetch_receipt(request, pk):
    """Подтянуть receipt_url из Stripe для существующего платежа."""
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    booking = get_object_or_404(Booking, pk=pk)

    if not booking.stripe_payment_id:
        return JsonResponse({'success': False, 'error': 'No Stripe payment ID'}, status=400)

    if booking.stripe_receipt_url:
        return JsonResponse({'success': True, 'receipt_url': booking.stripe_receipt_url})

    import stripe
    from django.conf import settings

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        pi = stripe.PaymentIntent.retrieve(booking.stripe_payment_id)
        if pi.latest_charge:
            charge = stripe.Charge.retrieve(pi.latest_charge)
            receipt_url = charge.receipt_url or ''
        else:
            receipt_url = ''

        if receipt_url:
            booking.stripe_receipt_url = receipt_url
            booking.save(update_fields=['stripe_receipt_url', 'updated_at'])
            return JsonResponse({'success': True, 'receipt_url': receipt_url})
        else:
            return JsonResponse({'success': False, 'error': 'No receipt available'}, status=404)

    except stripe.error.StripeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@method_decorator(staff_member_required, name='dispatch')
class ManagerUserCreateView(TemplateView):
    """Менеджер создаёт нового клиента под ключ."""
    template_name = 'backoffice/users/create.html'

    def get_context_data(self, **kwargs):
        from .forms import ManagerUserCreateForm
        context = super().get_context_data(**kwargs)
        context.setdefault('form', ManagerUserCreateForm())
        return context

    def post(self, request):
        from .forms import ManagerUserCreateForm
        form = ManagerUserCreateForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        user = form.save()
        messages.success(
            request,
            f'Customer {user.email} created. Share the password with them.',
        )

        if request.POST.get('then') == 'create_booking':
            return redirect(
                f"{request.build_absolute_uri('/backoffice/bookings/create/')}?user={user.pk}"
            )
        return redirect('backoffice:user_detail', pk=user.pk)


@method_decorator(staff_member_required, name='dispatch')
class ManagerBookingCreateView(TemplateView):
    """Менеджер создаёт бронирование от имени клиента."""
    template_name = 'backoffice/bookings/create.html'

    def get_context_data(self, **kwargs):
        from .forms import ManagerBookingCreateForm, ManagerUserCreateForm
        from services.models import Tariff
        context = super().get_context_data(**kwargs)

        initial = {}
        preselected_user_id = self.request.GET.get('user')
        if preselected_user_id:
            initial['user_id'] = preselected_user_id

        if 'form' not in context:
            context['form'] = ManagerBookingCreateForm(initial=initial)

        # Для autocomplete предзаполненного клиента — отдадим его в JSON виде
        context['preselected_user'] = None
        if preselected_user_id:
            try:
                u = User.objects.get(pk=preselected_user_id)
                context['preselected_user'] = {
                    'id': u.pk,
                    'email': u.email,
                    'name': u.get_full_name() or u.email,
                }
            except User.DoesNotExist:
                pass

        # Для авто-выбора единственного тарифа во фронте
        context['active_tariffs_count'] = Tariff.objects.filter(is_active=True).count()
        context['user_create_form'] = ManagerUserCreateForm()
        return context

    def post(self, request):
        from .forms import ManagerBookingCreateForm
        form = ManagerBookingCreateForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        booking = create_booking_from_manager_form(form, manager=request.user)

        if booking.payment_method == Booking.PaymentMethod.LK_INVOICE:
            messages.success(
                request,
                f'Booking #{booking.number} created — pending payment in customer cabinet.',
            )
        else:
            messages.success(
                request,
                f'Booking #{booking.number} created and activated ({booking.get_payment_method_display()}).',
            )
        return redirect('backoffice:booking_detail', pk=booking.pk)


@staff_member_required
def api_user_search(request):
    """Поиск клиента для autocomplete в форме создания брони."""
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    users = User.objects.filter(
        Q(email__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(phone__icontains=q)
    ).order_by('email')[:15]

    return JsonResponse({
        'results': [
            {
                'id': u.pk,
                'email': u.email,
                'name': u.get_full_name() or u.email,
                'phone': u.phone or '',
            }
            for u in users
        ]
    })


@staff_member_required
def api_user_create(request):
    """Inline-создание клиента из модалки на форме создания брони."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    from .forms import ManagerUserCreateForm
    form = ManagerUserCreateForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {'success': False, 'errors': {k: [str(e) for e in v] for k, v in form.errors.items()}},
            status=400,
        )

    user = form.save()
    return JsonResponse({
        'success': True,
        'user': {
            'id': user.pk,
            'email': user.email,
            'name': user.get_full_name() or user.email,
            'phone': user.phone or '',
        },
    })


@staff_member_required
def api_user_active_booking(request, pk):
    """Активное основное бронирование клиента (для extension-флоу).

    Возвращает данные о текущем юните клиента, если он есть. Используется
    на форме создания брони: если юнит занят выбранным клиентом, менеджер
    выбирает его → форма создаёт extension вместо новой брони.
    """
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    booking = (
        Booking.objects
        .filter(
            user=user,
            status=Booking.Status.PAID,
            parent_booking__isnull=True,
            storage_unit__isnull=False,
        )
        .select_related('storage_unit__section__location', 'tariff', 'period')
        .order_by('-end_date')
        .first()
    )

    if not booking:
        return JsonResponse({'active_booking': None})

    return JsonResponse({
        'active_booking': {
            'id': booking.pk,
            'number': booking.number,
            'unit_id': booking.storage_unit.pk,
            'unit_code': booking.storage_unit.full_code,
            'tariff_id': booking.tariff_id,
            'period_id': booking.period_id,
            'end_date': booking.end_date.isoformat(),
            'status': booking.status,
        }
    })


@staff_member_required
def api_tariff_info(request, pk):
    """Тариф + его периоды — для динамического обновления формы."""
    from services.models import Tariff
    try:
        tariff = Tariff.objects.select_related('service').prefetch_related('periods__price_tiers').get(pk=pk, is_active=True)
    except Tariff.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    periods = []
    for p in tariff.periods.filter(is_active=True).order_by('sort_order', 'duration_value'):
        periods.append({
            'id': p.pk,
            'name': p.name,
            'duration_display': p.duration_display,
            'base_price': str(p.base_price),
        })

    available = sum(
        1 for u in tariff.service.sections.filter(location=tariff.location, is_active=True).first().units.filter(is_active=True, is_available=True)
    ) if tariff.service.sections.filter(location=tariff.location, is_active=True).first() else 0

    return JsonResponse({
        'id': tariff.pk,
        'name': tariff.name,
        'service_type': tariff.service.service_type,
        'quantity_label': tariff.service.quantity_label or '',
        'available_units': tariff.available_units,
        'periods': periods,
    })


def create_booking_from_manager_form(form, manager):
    """Применить форму менеджера и создать Booking.

    Если выбранный storage_unit уже принадлежит клиенту как primary unit
    активного бронирования → создаём extension (продление). Иначе — новое
    бронирование.

    period_type=standard — цена из TariffPeriod, опционально override.
    period_type=custom   — ручные start/end + ручная price.
    Для cash/stripe_payment_link сразу активируем.
    Для lk_invoice оставляем PENDING — клиент платит из ЛК.
    """
    from decimal import Decimal as D
    cleaned = form.cleaned_data

    user = User.objects.get(pk=cleaned['user_id'])
    storage_unit = cleaned.get('storage_unit')
    payment_method = cleaned['payment_method']
    period_type = cleaned['period_type']
    period_choice = cleaned.get('period')
    quantity = cleaned['quantity']
    manual_price = cleaned.get('price_aed')
    override_price = cleaned.get('override_price')

    # Определить, это продление или новая бронь (по выбранному юниту).
    extension_parent = None
    if storage_unit:
        extension_parent = Booking.objects.filter(
            user=user,
            storage_unit=storage_unit,
            parent_booking__isnull=True,
            status=Booking.Status.PAID,
        ).select_related('tariff').first()

    if extension_parent:
        # === EXTENSION ===
        # Тариф наследуется от родителя. Quantity всегда 1 (продление одного юнита).
        tariff = extension_parent.tariff
        quantity = 1

        if period_type == form.PERIOD_TYPE_CUSTOM:
            start_date = cleaned['custom_start_date']
            end_date = cleaned['custom_end_date']
            price_aed = manual_price
            period = period_choice or extension_parent.period
        else:
            period = period_choice
            start_date = extension_parent.end_date
            end_date = period.calculate_end_date(start_date)
            if override_price and manual_price is not None:
                price_aed = manual_price
            else:
                price_aed = period.get_unit_price(1)

        unit_price = price_aed
        total_aed = price_aed  # Extension никогда не берёт депозит

        extension = Booking.objects.create(
            user=user,
            tariff=tariff,
            period=period,
            storage_unit=extension_parent.storage_unit,
            start_date=start_date,
            end_date=end_date,
            quantity=quantity,
            unit_price_aed=unit_price,
            price_aed=price_aed,
            addons_aed=D('0'),
            deposit_aed=D('0'),
            total_aed=total_aed,
            payment_method=payment_method,
            parent_booking=extension_parent,
            created_by_manager=manager,
        )

        if payment_method == Booking.PaymentMethod.LK_INVOICE:
            return extension

        extension.complete_extension_externally_paid(total_aed)
        extension.refresh_from_db()
        return extension

    # === NEW BOOKING ===
    tariff = cleaned['tariff']

    if period_type == form.PERIOD_TYPE_CUSTOM:
        start_date = cleaned['custom_start_date']
        end_date = cleaned['custom_end_date']
        price_aed = manual_price
        unit_price = (price_aed / quantity) if quantity else price_aed
        period = period_choice or tariff.periods.filter(is_active=True).first()
    else:
        period = period_choice
        start_date = timezone.now().date()
        end_date = period.calculate_end_date(start_date)
        if override_price and manual_price is not None:
            price_aed = manual_price
            unit_price = (price_aed / quantity) if quantity else price_aed
        else:
            unit_price = period.get_unit_price(quantity)
            price_aed = unit_price * quantity

    total_aed = price_aed  # без депозита

    booking = Booking.objects.create(
        user=user,
        tariff=tariff,
        period=period,
        start_date=start_date,
        end_date=end_date,
        quantity=quantity,
        unit_price_aed=unit_price,
        price_aed=price_aed,
        addons_aed=D('0'),
        deposit_aed=D('0'),
        total_aed=total_aed,
        payment_method=payment_method,
        created_by_manager=manager,
    )

    if payment_method == Booking.PaymentMethod.LK_INVOICE:
        return booking

    booking.activate_externally_paid(total_aed, storage_unit=storage_unit)
    booking.refresh_from_db()
    return booking