from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, ListView, DetailView
from django.db.models import Count, Q
from django.utils import timezone
from django.http import JsonResponse
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Статистика
        context['stats'] = {
            'active_bookings': Booking.objects.filter(
                status__in=[Booking.Status.PAID, Booking.Status.ACTIVE]
            ).count(),
            'pending_bookings': Booking.objects.filter(
                status=Booking.Status.PENDING
            ).count(),
            'today_visits': Visit.objects.filter(
                visited_at__date=today
            ).count(),
            'new_feedback': FeedbackRequest.objects.filter(
                status=FeedbackRequest.Status.NEW
            ).count(),
            'expiring_soon': Booking.objects.filter(
                status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
                end_date__lte=today + timedelta(days=7),
                end_date__gte=today
            ).count(),
        }

        # Последние заявки
        context['recent_feedback'] = FeedbackRequest.objects.filter(
            status=FeedbackRequest.Status.NEW
        ).order_by('-created_at')[:5]

        # Последние бронирования
        context['recent_bookings'] = Booking.objects.select_related(
            'user', 'tariff', 'storage_unit'
        ).order_by('-created_at')[:5]

        # Сегодняшние посещения
        context['today_visits_list'] = Visit.objects.filter(
            visited_at__date=today
        ).select_related('booking__user', 'booking__storage_unit').order_by('-visited_at')[:10]

        return context


@method_decorator(staff_member_required, name='dispatch')
class BookingListView(ListView):
    """Список бронирований"""
    model = Booking
    template_name = 'backoffice/bookings/list.html'
    context_object_name = 'bookings'
    paginate_by = 20

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'user', 'tariff', 'storage_unit', 'tariff__location'
        ).order_by('-created_at')

        # Фильтры
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(storage_unit__unit_number__icontains=search) |
                Q(pk__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Booking.Status.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')
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
            'tariff', 'storage_unit'
        ).order_by('-created_at')[:10]
        return context


@method_decorator(staff_member_required, name='dispatch')
class VisitListView(ListView):
    """История посещений"""
    model = Visit
    template_name = 'backoffice/visits/list.html'
    context_object_name = 'visits'
    paginate_by = 20

    def get_queryset(self):
        qs = Visit.objects.select_related(
            'booking__user', 'booking__storage_unit', 'scanned_by'
        ).order_by('-visited_at')

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(booking__user__email__icontains=search) |
                Q(visitor_name__icontains=search) |
                Q(booking__storage_unit__unit_number__icontains=search)
            )

        visitor_type = self.request.GET.get('type')
        if visitor_type:
            qs = qs.filter(visitor_type=visitor_type)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['current_type'] = self.request.GET.get('type', '')
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

    def get_queryset(self):
        qs = StorageUnit.objects.select_related(
            'section', 'section__location', 'section__service'
        ).order_by('section__location', 'section__sort_order', 'unit_number')

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

        # Поиск
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(unit_number__icontains=search)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['locations'] = Location.objects.filter(is_active=True)
        context['current_location'] = self.request.GET.get('location', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['search'] = self.request.GET.get('search', '')

        # Статистика
        context['stats'] = {
            'total': StorageUnit.objects.filter(is_active=True).count(),
            'available': StorageUnit.objects.filter(is_active=True, is_available=True).count(),
            'occupied': StorageUnit.objects.filter(is_active=True, is_available=False).count(),
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
    """Освободить ячейку после expired бронирования"""
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)

        if booking.status not in [Booking.Status.EXPIRED, Booking.Status.COMPLETED]:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Booking is still active'}, status=400)
            messages.error(request, 'Cannot release active booking')
            return redirect('backoffice:booking_detail', pk=pk)

        # Освобождаем ячейку
        if booking.storage_unit:
            booking.storage_unit.is_available = True
            booking.storage_unit.save(update_fields=['is_available'])

        # Меняем статус на COMPLETED
        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=['status'])

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        messages.success(request, f'Unit {booking.storage_unit} released successfully')
        return redirect('backoffice:booking_detail', pk=pk)

    return JsonResponse({'success': False}, status=400)