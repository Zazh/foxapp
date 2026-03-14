from django.db import migrations


def populate_snapshots(apps, schema_editor):
    Visit = apps.get_model('visits', 'Visit')
    for visit in Visit.objects.filter(unit_code='').select_related(
        'access_token__storage_unit__section__location',
        'booking__storage_unit__section__location',
        'scanned_by',
    ):
        unit = None
        if visit.access_token and visit.access_token.storage_unit:
            unit = visit.access_token.storage_unit
        elif visit.booking and visit.booking.storage_unit:
            unit = visit.booking.storage_unit

        if unit:
            visit.unit_code = f"{unit.section.location.name[:3].upper()}-{unit.section.name}-{unit.unit_number}"
            visit.location_name = unit.section.location.name

        if visit.scanned_by:
            name = f"{visit.scanned_by.first_name} {visit.scanned_by.last_name}".strip()
            visit.scanned_by_name = name or visit.scanned_by.email

        visit.save(update_fields=['unit_code', 'location_name', 'scanned_by_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0004_visit_location_name_visit_scanned_by_name_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_snapshots, migrations.RunPython.noop),
    ]
