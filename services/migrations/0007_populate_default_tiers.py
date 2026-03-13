"""
Data migration: create default TariffPriceTier for each existing TariffPeriod.
Each period gets a tier with min_units=1, max_units=None (covers all quantities).
"""
from django.db import migrations


def populate_default_tiers(apps, schema_editor):
    TariffPeriod = apps.get_model('services', 'TariffPeriod')
    TariffPriceTier = apps.get_model('services', 'TariffPriceTier')

    for period in TariffPeriod.objects.all():
        if not TariffPriceTier.objects.filter(period=period).exists():
            TariffPriceTier.objects.create(
                period=period,
                min_units=1,
                max_units=None,
                price_per_unit_aed=period.price_aed,
                price_per_unit_usd=period.price_usd,
            )


def reverse_populate(apps, schema_editor):
    TariffPriceTier = apps.get_model('services', 'TariffPriceTier')
    TariffPriceTier.objects.filter(min_units=1, max_units__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0006_tariffpricetier'),
    ]

    operations = [
        migrations.RunPython(populate_default_tiers, reverse_populate),
    ]
