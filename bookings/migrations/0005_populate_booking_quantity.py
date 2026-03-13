"""
Data migration: set quantity=1 and unit_price_aed=price_aed for existing bookings.
Also create BookingUnit from existing storage_unit FK.
"""
from django.db import migrations


def populate_booking_data(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    BookingUnit = apps.get_model('bookings', 'BookingUnit')

    for booking in Booking.objects.all():
        updated_fields = []

        if booking.quantity != 1:
            booking.quantity = 1
            updated_fields.append('quantity')

        if booking.unit_price_aed is None:
            booking.unit_price_aed = booking.price_aed
            updated_fields.append('unit_price_aed')

        if updated_fields:
            booking.save(update_fields=updated_fields)

        # Create BookingUnit from existing FK
        if booking.storage_unit_id and not BookingUnit.objects.filter(
            booking=booking, storage_unit_id=booking.storage_unit_id
        ).exists():
            BookingUnit.objects.create(
                booking=booking,
                storage_unit_id=booking.storage_unit_id,
            )


def reverse_populate(apps, schema_editor):
    BookingUnit = apps.get_model('bookings', 'BookingUnit')
    BookingUnit.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0004_booking_quantity_and_units'),
    ]

    operations = [
        migrations.RunPython(populate_booking_data, reverse_populate),
    ]
