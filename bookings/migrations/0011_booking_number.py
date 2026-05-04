from django.db import migrations, models


def populate_numbers(apps, schema_editor):
    """Сквозная нумерация существующих бронирований по порядку pk."""
    Booking = apps.get_model('bookings', 'Booking')
    for index, booking in enumerate(Booking.objects.order_by('pk'), start=1):
        booking.number = f"{index:05d}"
        booking.save(update_fields=['number'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0010_add_booking_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='number',
            field=models.CharField(
                max_length=5, blank=True, default='',
                verbose_name='Booking number',
                help_text='Human-readable 5-digit ID shown to customers',
            ),
        ),
        migrations.RunPython(populate_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='booking',
            name='number',
            field=models.CharField(
                max_length=5, unique=True,
                verbose_name='Booking number',
                help_text='Human-readable 5-digit ID shown to customers',
            ),
        ),
    ]
