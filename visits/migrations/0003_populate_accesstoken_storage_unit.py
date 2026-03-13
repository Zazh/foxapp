"""
Data migration: set AccessToken.storage_unit from booking.storage_unit for existing tokens.
"""
from django.db import migrations


def populate_token_storage_unit(apps, schema_editor):
    AccessToken = apps.get_model('visits', 'AccessToken')

    for token in AccessToken.objects.select_related('booking').all():
        if token.storage_unit_id is None and token.booking.storage_unit_id:
            token.storage_unit_id = token.booking.storage_unit_id
            token.save(update_fields=['storage_unit_id'])


def reverse_populate(apps, schema_editor):
    AccessToken = apps.get_model('visits', 'AccessToken')
    AccessToken.objects.update(storage_unit_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('visits', '0002_accesstoken_storage_unit'),
    ]

    operations = [
        migrations.RunPython(populate_token_storage_unit, reverse_populate),
    ]
