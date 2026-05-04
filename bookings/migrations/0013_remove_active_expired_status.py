from django.db import migrations, models


def collapse_active_expired_to_paid(apps, schema_editor):
    """ACTIVE и EXPIRED больше не существуют — конвертируем в PAID.

    Booking теперь хранит только статусы оплаты. "Active vs expired" —
    derivable от start_date/end_date через Booking.active_qs() / overdue_qs().
    """
    Booking = apps.get_model('bookings', 'Booking')
    Booking.objects.filter(status__in=['active', 'expired']).update(status='paid')


def restore_active_expired(apps, schema_editor):
    """Reverse: подгоним PAID обратно по датам (best-effort)."""
    from django.utils import timezone
    Booking = apps.get_model('bookings', 'Booking')
    today = timezone.now().date()
    Booking.objects.filter(
        status='paid', parent_booking__isnull=True,
        start_date__lte=today, end_date__gte=today,
    ).update(status='active')
    Booking.objects.filter(
        status='paid', parent_booking__isnull=True,
        end_date__lt=today,
    ).update(status='expired')


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0012_booking_payment_method'),
    ]

    operations = [
        migrations.RunPython(collapse_active_expired_to_paid, restore_active_expired),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('pending', 'Pending payment'),
                    ('paid', 'Paid'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending',
                verbose_name='Status',
            ),
        ),
    ]
