from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from bookings.models import Booking
from notifications.services import notify_booking_expiring
from notifications.models import NotificationTemplate


class Command(BaseCommand):
    help = 'Send notifications for expiring/expired bookings'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        self.stdout.write(f'Date: {today}')
        self.stdout.write(f'Dry run: {dry_run}\n')

        # Напоминания за 7, 3, 1 день до истечения
        reminder_days = [7, 3, 1]

        for days in reminder_days:
            target_date = today + timedelta(days=days)

            bookings = Booking.objects.filter(
                end_date=target_date,
                status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
                parent_booking__isnull=True
            ).select_related('user', 'tariff', 'storage_unit')

            self.stdout.write(f'=== Expiring in {days} days ({target_date}) ===')
            self.stdout.write(f'Found: {bookings.count()} bookings')

            for booking in bookings:
                self.stdout.write(f'  - {booking.user.email}: Unit {booking.storage_unit}')

                if not dry_run:
                    try:
                        notify_booking_expiring(booking, days)
                        self.stdout.write(self.style.SUCCESS(f'    ✓ Notification sent'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'    ✗ Error: {e}'))

        # Истёкшие бронирования - помечаем как EXPIRED (НЕ освобождаем ячейку!)
        expired_bookings = Booking.objects.filter(
            end_date__lt=today,  # Все где end_date в прошлом
            status__in=[Booking.Status.PAID, Booking.Status.ACTIVE],
            parent_booking__isnull=True
        ).select_related('user', 'tariff', 'storage_unit')

        self.stdout.write(f'\n=== Expired bookings ===')
        self.stdout.write(f'Found: {expired_bookings.count()} bookings')

        for booking in expired_bookings:
            days_overdue = (today - booking.end_date).days
            self.stdout.write(f'  - {booking.user.email}: Unit {booking.storage_unit} (overdue {days_overdue} days)')

            if not dry_run:
                try:
                    # Меняем статус на EXPIRED, но НЕ освобождаем ячейку
                    booking.status = Booking.Status.EXPIRED
                    booking.save(update_fields=['status'])

                    # Уведомление отправляем только в первый день (когда только стало expired)
                    if days_overdue == 1:
                        from notifications.services import NotificationService

                        NotificationService.send(
                            user=booking.user,
                            notification_type=NotificationTemplate.NotificationType.BOOKING_EXPIRED,
                            context_data={
                                'booking': booking,
                                'unit': booking.storage_unit,
                                'end_date': booking.end_date,
                            }
                        )
                        self.stdout.write(self.style.SUCCESS(f'    ✓ Marked as EXPIRED, notification sent'))
                    else:
                        self.stdout.write(self.style.SUCCESS(f'    ✓ Marked as EXPIRED'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    ✗ Error: {e}'))

        self.stdout.write(self.style.SUCCESS('\n=== Done ==='))