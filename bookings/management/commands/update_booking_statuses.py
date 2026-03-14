from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Booking


class Command(BaseCommand):
    help = 'Transition booking statuses: paid→active (start_date reached), active→expired (end_date passed).'

    def handle(self, *args, **options):
        today = timezone.now().date()

        # paid → active (start_date reached, only non-extensions)
        to_activate = Booking.objects.filter(
            status=Booking.Status.PAID,
            parent_booking__isnull=True,
            start_date__lte=today,
        )
        activated = 0
        for booking in to_activate:
            booking.activate()
            activated += 1

        # active → expired (end_date passed, units stay occupied!)
        to_expire = Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            end_date__lt=today,
        )
        expired = 0
        for booking in to_expire:
            booking.expire()
            expired += 1

        if activated or expired:
            self.stdout.write(self.style.SUCCESS(
                f'Activated: {activated}, Expired: {expired}'
            ))
        else:
            self.stdout.write('No status transitions needed.')
