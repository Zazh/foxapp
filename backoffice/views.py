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
                status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
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
            'expired_unreleased': Booking.objects.filter(
                status=Booking.Status.EXPIRED,
                parent_booking__isnull=True,
            ).count(),
            'expiring_soon': Booking.objects.filter(
                status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
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
            bookings__status=Booking.Status.EXPIRED,
            bookings__parent_booking__isnull=True,
        ).distinct().count()
        expiring_units = storage_qs.filter(
            is_available=False,
            bookings__status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
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
        ).order_by('-created_at')[:5]

        # Expired (unreleased) — требуют внимания менеджера
        context['expired_bookings'] = Booking.objects.filter(
            status=Booking.Status.EXPIRED,
            parent_booking__isnull=True,
        ).select_related('user').order_by('end_date')

        # Expiring soon (14 дней)
        context['expiring_bookings'] = Booking.objects.filter(
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
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
            qs = Booking.objects.filter(
                status=Booking.Status.EXPIRED,
                parent_booking__isnull=True,
            ).order_by('end_date')
        elif status == 'expiring_soon':
            qs = Booking.objects.filter(
                status=Booking.Status.ACTIVE,
                parent_booking__isnull=True,
                end_date__gte=today,
                end_date__lte=today + timedelta(days=14),
            ).order_by('end_date')
        elif status == 'active':
            qs = Booking.objects.filter(
                status=Booking.Status.ACTIVE,
                parent_booking__isnull=True,
            ).order_by('end_date')
        else:
            # По умолчанию: expired + expiring + active, с приоритетной сортировкой
            qs = Booking.objects.filter(
                status__in=[Booking.Status.ACTIVE, Booking.Status.EXPIRED],
                parent_booking__isnull=True,
            ).annotate(
                sort_priority=Case(
                    When(status=Booking.Status.EXPIRED, then=Value(0)),
                    When(
                        status=Booking.Status.ACTIVE,
                        end_date__lte=today + timedelta(days=7),
                        then=Value(1),
                    ),
                    When(
                        status=Booking.Status.ACTIVE,
                        end_date__lte=today + timedelta(days=14),
                        then=Value(2),
                    ),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
            ).order_by('sort_priority', 'end_date')

        qs = qs.select_related('user')

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

        # Счётчики для фильтров
        base = Booking.objects.filter(parent_booking__isnull=True)
        context['stats'] = {
            'active': base.filter(status=Booking.Status.ACTIVE).count(),
            'expired': base.filter(status=Booking.Status.EXPIRED).count(),
            'expiring_soon': base.filter(
                status=Booking.Status.ACTIVE,
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
            'user'
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

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(stripe_payment_id__icontains=search) |
                Q(stripe_session_id__icontains=search) |
                Q(pk__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')

        # Статистика
        context['stats'] = {
            'total_paid': Booking.objects.filter(paid_at__isnull=False).count(),
            'total_revenue': Booking.objects.filter(
                paid_at__isnull=False
            ).aggregate(total=Sum('total_aed'))['total'] or 0,
            'pending': Booking.objects.filter(
                status=Booking.Status.PENDING,
                expires_at__gt=now,
            ).count(),
            'failed': Booking.objects.filter(
                status=Booking.Status.CANCELLED,
                paid_at__isnull=True,
            ).count(),
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
        context['bookings'] = self.object.bookings.order_by('-created_at')[:10]
        return context


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
            'booking__user'
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

        # Subquery: end_date текущего бронирования (paid/active/expired)
        current_booking_end = Booking.objects.filter(
            storage_unit=OuterRef('pk'),
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE, Booking.Status.EXPIRED],
            parent_booking__isnull=True,
        ).order_by('-created_at').values('end_date')[:1]

        # Subquery: статус текущего бронирования
        current_booking_status = Booking.objects.filter(
            storage_unit=OuterRef('pk'),
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE, Booking.Status.EXPIRED],
            parent_booking__isnull=True,
        ).order_by('-created_at').values('status')[:1]

        qs = StorageUnit.objects.filter(
            section__location__location_type__in=self.STORAGE_LOCATION_TYPES,
        ).select_related(
            'section', 'section__location', 'section__service'
        ).annotate(
            booking_end_date=Subquery(current_booking_end),
            booking_status=Subquery(current_booking_status, output_field=CharField()),
            sort_priority=Case(
                # Expired — самый высокий приоритет
                When(
                    is_available=False,
                    booking_status=Booking.Status.EXPIRED,
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
                bookings__status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
                bookings__parent_booking__isnull=True,
                bookings__end_date__gte=today,
                bookings__end_date__lte=today + timedelta(days=14),
            ).distinct()
        elif status == 'expired':
            qs = qs.filter(
                is_available=False,
                bookings__status=Booking.Status.EXPIRED,
                bookings__parent_booking__isnull=True,
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
                bookings__status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
                bookings__parent_booking__isnull=True,
                bookings__end_date__gte=today,
                bookings__end_date__lte=today + timedelta(days=14),
            ).distinct().count(),
            'expired': storage_units.filter(
                is_available=False,
                bookings__status=Booking.Status.EXPIRED,
                bookings__parent_booking__isnull=True,
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
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE]
        ).select_related('user', 'tariff').first()

        # История бронирований
        context['booking_history'] = Booking.objects.filter(
            storage_unit=self.object
        ).select_related('user', 'tariff').order_by('-created_at')[:10]

        # История посещений
        context['recent_visits'] = Visit.objects.filter(
            booking__storage_unit=self.object
        ).select_related('booking__user').order_by('-visited_at')[:10]

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

        if booking.status not in [Booking.Status.EXPIRED, Booking.Status.ACTIVE]:
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

    if booking.status not in [Booking.Status.PAID, Booking.Status.ACTIVE, Booking.Status.EXPIRED]:
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