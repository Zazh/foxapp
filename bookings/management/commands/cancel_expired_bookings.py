from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking


class Command(BaseCommand):
    help = 'Cancel pending bookings that have exceeded the 30-minute payment window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview which bookings would be cancelled without making changes.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options['dry_run']

        expired_pending = Booking.objects.filter(
            status=Booking.Status.PENDING,
            expires_at__lt=now,
        )

        count = expired_pending.count()

        if count == 0:
            self.stdout.write('No expired pending bookings found.')
            return

        if dry_run:
            self.stdout.write(f'[DRY RUN] Would cancel {count} expired pending booking(s):')
            for b in expired_pending.select_related('user', 'tariff'):
                self.stdout.write(f'  #{b.pk} — {b.user.email} — {b.tariff_name or b.tariff.name} (expired {b.expires_at})')
            return

        cancelled = 0
        for booking in expired_pending:
            try:
                with transaction.atomic():
                    booking.cancel()
                cancelled += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cancelling #{booking.pk}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Cancelled {cancelled} expired pending booking(s).'))
