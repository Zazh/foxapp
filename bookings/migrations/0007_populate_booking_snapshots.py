from django.db import migrations


def populate_snapshots(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    BookingUnit = apps.get_model('bookings', 'BookingUnit')

    for booking in Booking.objects.filter(tariff_name='').select_related(
        'tariff__service',
        'tariff__location',
        'period',
        'storage_unit__section__location',
    ):
        if booking.tariff:
            booking.tariff_name = booking.tariff.name or ''
            if booking.tariff.service:
                booking.service_name = booking.tariff.service.name or ''
            if booking.tariff.location:
                booking.location_name = booking.tariff.location.name or ''

        if booking.period:
            dur_type = booking.period.duration_type
            dur_val = booking.period.duration_value
            if dur_type == 'days':
                label = f"{dur_val} {'day' if dur_val == 1 else 'days'}"
            else:
                label = f"{dur_val} {'month' if dur_val == 1 else 'months'}"
            booking.period_label = label

        # Unit codes from BookingUnit through table
        bu_units = list(
            BookingUnit.objects.filter(booking=booking)
            .select_related('storage_unit__section__location')
            .order_by('pk')
        )
        if bu_units:
            codes = []
            for bu in bu_units:
                u = bu.storage_unit
                loc_prefix = u.section.location.name[:3].upper() if u.section and u.section.location else '???'
                sec_name = u.section.name if u.section else '?'
                codes.append(f"{loc_prefix}-{sec_name}-{u.unit_number}")
            booking.unit_codes = ', '.join(codes)
        elif booking.storage_unit:
            u = booking.storage_unit
            if u.section and u.section.location:
                loc_prefix = u.section.location.name[:3].upper()
                booking.unit_codes = f"{loc_prefix}-{u.section.name}-{u.unit_number}"

        booking.save(update_fields=[
            'tariff_name', 'service_name', 'location_name',
            'period_label', 'unit_codes',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0006_booking_location_name_booking_period_label_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_snapshots, migrations.RunPython.noop),
    ]
