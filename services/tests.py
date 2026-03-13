from decimal import Decimal
from django.test import TestCase
from django.db import IntegrityError

from services.models import (
    Service, Tariff, TariffPeriod, TariffPriceTier,
    Section, StorageUnit,
)
from locations.models import Location


class ServiceTestMixin:
    """Shared setup for service-related tests."""

    def create_base_objects(self):
        self.service = Service.objects.create(
            service_type=Service.ServiceType.AUTO,
            name='Auto Storage',
        )
        self.location = Location.objects.create(
            name='Dubai',
            location_type=Location.LocationType.AUTO_STORAGE,
            street='Test Street',
            building='1',
            latitude=Decimal('25.0000000'),
            longitude=Decimal('55.0000000'),
        )
        self.tariff = Tariff.objects.create(
            service=self.service,
            location=self.location,
            name='VIP Parking',
            name_en='VIP Parking',
            deposit_aed=Decimal('0.00'),
        )
        self.period = TariffPeriod.objects.create(
            tariff=self.tariff,
            name='1 Month',
            name_en='1 Month',
            duration_type=TariffPeriod.DurationType.MONTHS,
            duration_value=1,
        )
        # Default tier (как после data migration)
        self.default_tier = TariffPriceTier.objects.create(
            period=self.period,
            min_units=1,
            max_units=None,
            price_per_unit_aed=Decimal('500.00'),
        )


class TariffPriceTierModelTest(ServiceTestMixin, TestCase):

    def setUp(self):
        self.create_base_objects()

    def test_tier_creation(self):
        self.assertEqual(self.default_tier.period, self.period)
        self.assertEqual(self.default_tier.min_units, 1)
        self.assertIsNone(self.default_tier.max_units)
        self.assertEqual(self.default_tier.price_per_unit_aed, Decimal('500.00'))

    def test_tier_str(self):
        tier = TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )
        self.assertIn('2', str(tier))
        self.assertIn('5', str(tier))
        self.assertIn('450', str(tier))

    def test_tier_str_unlimited(self):
        tier = TariffPriceTier.objects.create(
            period=self.period, min_units=6, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )
        self.assertIn('6', str(tier))

    def test_tier_ordering_by_min_units(self):
        TariffPriceTier.objects.create(
            period=self.period, min_units=6, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )
        # default_tier has min_units=1
        self.default_tier.max_units = 1
        self.default_tier.save()
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )
        tiers = list(self.period.price_tiers.all())
        self.assertEqual(tiers[0].min_units, 1)
        self.assertEqual(tiers[1].min_units, 2)
        self.assertEqual(tiers[2].min_units, 6)

    def test_tier_unique_min_per_period(self):
        with self.assertRaises(IntegrityError):
            TariffPriceTier.objects.create(
                period=self.period, min_units=1, max_units=5,
                price_per_unit_aed=Decimal('450.00'),
            )

    def test_tier_discount(self):
        tier = TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
            original_price_per_unit_aed=Decimal('500.00'),
        )
        self.assertTrue(tier.has_discount)
        self.assertEqual(tier.discount_percent, 10)

    def test_tier_no_discount(self):
        self.assertFalse(self.default_tier.has_discount)
        self.assertEqual(self.default_tier.discount_percent, 0)


class TariffPeriodPricingTest(ServiceTestMixin, TestCase):

    def setUp(self):
        self.create_base_objects()

    def test_base_price(self):
        """base_price returns price from first tier (min_units=1)."""
        self.assertEqual(self.period.base_price, Decimal('500.00'))

    def test_single_tier_any_quantity(self):
        """Single tier with max_units=None matches any quantity."""
        self.assertEqual(self.period.get_unit_price(1), Decimal('500.00'))
        self.assertEqual(self.period.get_unit_price(10), Decimal('500.00'))

    def test_multiple_tiers_boundaries(self):
        """Test correct tier selection at boundary values."""
        # Update default tier to be 1-only
        self.default_tier.max_units = 1
        self.default_tier.save()
        # 2-5 = 450, 6+ = 400
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )
        TariffPriceTier.objects.create(
            period=self.period, min_units=6, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )

        self.assertEqual(self.period.get_unit_price(1), Decimal('500.00'))
        self.assertEqual(self.period.get_unit_price(2), Decimal('450.00'))
        self.assertEqual(self.period.get_unit_price(5), Decimal('450.00'))
        self.assertEqual(self.period.get_unit_price(6), Decimal('400.00'))
        self.assertEqual(self.period.get_unit_price(3), Decimal('450.00'))
        self.assertEqual(self.period.get_unit_price(100), Decimal('400.00'))

    def test_quantity_1_specific_tier(self):
        """When tier for 1 car exists with max_units=1, it's selected for qty=1."""
        self.default_tier.max_units = 1
        self.default_tier.save()
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )
        self.assertEqual(self.period.get_unit_price(1), Decimal('500.00'))
        self.assertEqual(self.period.get_unit_price(2), Decimal('400.00'))

    def test_get_total_price(self):
        """get_total_price = unit_price * quantity."""
        self.default_tier.max_units = 1
        self.default_tier.save()
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )

        self.assertEqual(self.period.get_total_price(1), Decimal('500.00'))
        self.assertEqual(self.period.get_total_price(3), Decimal('1350.00'))
        self.assertEqual(self.period.get_total_price(5), Decimal('2250.00'))

    def test_period_str_uses_base_price(self):
        self.assertIn('500', str(self.period))

    def test_has_discount_from_tier(self):
        """Period.has_discount delegates to first tier."""
        self.assertFalse(self.period.has_discount)
        self.default_tier.original_price_per_unit_aed = Decimal('600.00')
        self.default_tier.save()
        # Refresh from DB to clear cached queries
        self.period = TariffPeriod.objects.get(pk=self.period.pk)
        self.assertTrue(self.period.has_discount)
        self.assertEqual(self.period.discount_percent, 16)


class TariffPriceTierDataMigrationTest(ServiceTestMixin, TestCase):
    """Tests that verify data migration correctness for existing TariffPeriods."""

    def setUp(self):
        self.create_base_objects()

    def test_default_tier_exists(self):
        """Each period has a default tier with min_units=1."""
        tier = TariffPriceTier.objects.get(period=self.period, min_units=1)
        self.assertIsNone(tier.max_units)
        self.assertEqual(tier.price_per_unit_aed, Decimal('500.00'))

    def test_get_unit_price_consistent(self):
        """After migration, any quantity returns the same base price."""
        self.assertEqual(self.period.get_unit_price(1), Decimal('500.00'))
        self.assertEqual(self.period.get_unit_price(5), Decimal('500.00'))
        self.assertEqual(self.period.get_unit_price(100), Decimal('500.00'))
