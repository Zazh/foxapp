from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, RequestFactory, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking, BookingAddon, BookingUnit
from services.models import (
    Service, Tariff, TariffPeriod, TariffPriceTier,
    AddonService, Section, StorageUnit,
)
from locations.models import Location


class BookingTestMixin:
    """Shared setup for booking tests."""

    def create_base_objects(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
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
            deposit_aed=Decimal('200.00'),
        )
        self.period = TariffPeriod.objects.create(
            tariff=self.tariff,
            name='1 Month',
            name_en='1 Month',
            duration_type=TariffPeriod.DurationType.MONTHS,
            duration_value=1,
        )
        # Default tier
        TariffPriceTier.objects.create(
            period=self.period,
            min_units=1,
            max_units=None,
            price_per_unit_aed=Decimal('500.00'),
        )
        # Create storage section and units
        self.section = Section.objects.create(
            location=self.location,
            service=self.service,
            name='A',
        )
        self.units = []
        for i in range(1, 11):
            unit = StorageUnit.objects.create(
                section=self.section,
                unit_number=f'{i:02d}',
            )
            self.units.append(unit)

    def create_booking(self, quantity=1, **kwargs):
        defaults = {
            'user': self.user,
            'tariff': self.tariff,
            'period': self.period,
            'start_date': timezone.now().date(),
            'price_aed': Decimal('500.00') * quantity,
            'unit_price_aed': Decimal('500.00'),
            'addons_aed': Decimal('0.00'),
            'deposit_aed': self.tariff.deposit_aed,
            'total_aed': Decimal('500.00') * quantity + self.tariff.deposit_aed,
            'quantity': quantity,
        }
        defaults.update(kwargs)
        return Booking.objects.create(**defaults)


class BookingQuantityTest(BookingTestMixin, TestCase):

    def setUp(self):
        self.create_base_objects()

    def test_default_quantity_is_1(self):
        booking = Booking.objects.create(
            user=self.user,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date(),
            price_aed=Decimal('500.00'),
            unit_price_aed=Decimal('500.00'),
            addons_aed=Decimal('0.00'),
            deposit_aed=Decimal('200.00'),
            total_aed=Decimal('700.00'),
        )
        self.assertEqual(booking.quantity, 1)

    def test_booking_with_quantity(self):
        booking = self.create_booking(quantity=3)
        self.assertEqual(booking.quantity, 3)

    def test_unit_price_stored(self):
        booking = self.create_booking(
            quantity=3,
            unit_price_aed=Decimal('450.00'),
            price_aed=Decimal('1350.00'),
            total_aed=Decimal('1550.00'),
        )
        self.assertEqual(booking.unit_price_aed, Decimal('450.00'))
        self.assertEqual(booking.price_aed, Decimal('1350.00'))

    def test_total_calculation_with_quantity(self):
        """total = price_aed + addons + deposit (price_aed already includes qty)."""
        booking = self.create_booking(
            quantity=3,
            unit_price_aed=Decimal('450.00'),
            price_aed=Decimal('1350.00'),  # 450 * 3
            addons_aed=Decimal('100.00'),
            deposit_aed=Decimal('200.00'),
            total_aed=Decimal('1650.00'),  # 1350 + 100 + 200
        )
        self.assertEqual(booking.total_aed, Decimal('1650.00'))

    def test_deposit_not_multiplied_by_quantity(self):
        """Deposit stays fixed regardless of quantity."""
        booking = self.create_booking(quantity=5)
        self.assertEqual(booking.deposit_aed, Decimal('200.00'))


class BookingUnitTest(BookingTestMixin, TestCase):

    def setUp(self):
        self.create_base_objects()

    def test_booking_unit_creation(self):
        booking = self.create_booking()
        bu = BookingUnit.objects.create(
            booking=booking,
            storage_unit=self.units[0],
        )
        self.assertEqual(bu.booking, booking)
        self.assertEqual(bu.storage_unit, self.units[0])

    def test_assign_storage_units_single(self):
        booking = self.create_booking(quantity=1)
        result = booking.assign_storage_units()
        self.assertTrue(result)
        self.assertEqual(booking.storage_unit, self.units[0])
        self.assertEqual(booking.booking_units.count(), 1)
        self.assertFalse(
            StorageUnit.objects.get(pk=self.units[0].pk).is_available
        )

    def test_assign_storage_units_multiple(self):
        booking = self.create_booking(quantity=3)
        result = booking.assign_storage_units()
        self.assertTrue(result)
        self.assertEqual(booking.booking_units.count(), 3)
        # Primary unit set for backward compat
        self.assertIsNotNone(booking.storage_unit)
        # All 3 units marked unavailable
        for i in range(3):
            self.assertFalse(
                StorageUnit.objects.get(pk=self.units[i].pk).is_available
            )
        # Remaining units still available
        self.assertTrue(
            StorageUnit.objects.get(pk=self.units[3].pk).is_available
        )

    def test_assign_storage_units_not_enough(self):
        """Returns False if not enough units available."""
        booking = self.create_booking(quantity=20)
        result = booking.assign_storage_units()
        self.assertFalse(result)

    def test_cancel_releases_all_units(self):
        booking = self.create_booking(quantity=3)
        booking.assign_storage_units()
        booking.cancel()
        # All units should be available again
        for i in range(3):
            self.assertTrue(
                StorageUnit.objects.get(pk=self.units[i].pk).is_available
            )
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_mark_as_paid_assigns_units(self):
        """mark_as_paid should call assign_storage_units."""
        booking = self.create_booking(quantity=2)
        booking.mark_as_paid('test_payment_123')
        self.assertEqual(booking.booking_units.count(), 2)
        self.assertIsNotNone(booking.storage_unit)

    def test_complete_releases_all_units(self):
        """When booking completes via complete(), all units become available."""
        booking = self.create_booking(quantity=2)
        booking.assign_storage_units()
        booking.status = Booking.Status.ACTIVE
        booking.save(update_fields=['status'])
        booking.complete()
        for bu in booking.booking_units.all():
            self.assertTrue(
                StorageUnit.objects.get(pk=bu.storage_unit_id).is_available
            )
        self.assertEqual(booking.status, Booking.Status.COMPLETED)


class BookingWithTieredPricingTest(BookingTestMixin, TestCase):
    """Integration test: tiers + booking creation."""

    def setUp(self):
        self.create_base_objects()
        # Override default tier to 1-only, add volume tiers
        default_tier = self.period.price_tiers.get(min_units=1)
        default_tier.max_units = 1
        default_tier.save()
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )
        TariffPriceTier.objects.create(
            period=self.period, min_units=6, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )

    def test_single_car_booking(self):
        unit_price = self.period.get_unit_price(1)
        booking = self.create_booking(
            quantity=1,
            unit_price_aed=unit_price,
            price_aed=unit_price * 1,
            total_aed=unit_price * 1 + self.tariff.deposit_aed,
        )
        self.assertEqual(booking.unit_price_aed, Decimal('500.00'))
        self.assertEqual(booking.price_aed, Decimal('500.00'))
        self.assertEqual(booking.total_aed, Decimal('700.00'))

    def test_three_car_booking(self):
        qty = 3
        unit_price = self.period.get_unit_price(qty)
        booking = self.create_booking(
            quantity=qty,
            unit_price_aed=unit_price,
            price_aed=unit_price * qty,
            total_aed=unit_price * qty + self.tariff.deposit_aed,
        )
        self.assertEqual(booking.unit_price_aed, Decimal('450.00'))
        self.assertEqual(booking.price_aed, Decimal('1350.00'))
        self.assertEqual(booking.total_aed, Decimal('1550.00'))

    def test_six_car_booking(self):
        qty = 6
        unit_price = self.period.get_unit_price(qty)
        booking = self.create_booking(
            quantity=qty,
            unit_price_aed=unit_price,
            price_aed=unit_price * qty,
            total_aed=unit_price * qty + self.tariff.deposit_aed,
        )
        self.assertEqual(booking.unit_price_aed, Decimal('400.00'))
        self.assertEqual(booking.price_aed, Decimal('2400.00'))
        self.assertEqual(booking.total_aed, Decimal('2600.00'))


class BookingCreateViewTest(BookingTestMixin, TestCase):
    """End-to-end tests: POST to BookingCreateView with quantity."""

    def setUp(self):
        self.create_base_objects()
        # Set up tiered pricing: 1=500, 2-5=450, 6+=400
        default_tier = self.period.price_tiers.get(min_units=1)
        default_tier.max_units = 1
        default_tier.save()
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=5,
            price_per_unit_aed=Decimal('450.00'),
        )
        TariffPriceTier.objects.create(
            period=self.period, min_units=6, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('booking_create', kwargs={
            'service_type': 'auto',
            'slug': self.tariff.slug,
        })

    def test_post_single_car_default(self):
        """POST without quantity defaults to 1."""
        resp = self.client.post(self.url, {'period': self.period.id})
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 1)
        self.assertEqual(booking.unit_price_aed, Decimal('500.00'))
        self.assertEqual(booking.price_aed, Decimal('500.00'))
        self.assertEqual(booking.deposit_aed, Decimal('200.00'))
        self.assertEqual(booking.total_aed, Decimal('700.00'))

    def test_post_3_cars_tier_applied(self):
        """POST with quantity=3 uses 2-5 tier (450 AED)."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '3',
        })
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 3)
        self.assertEqual(booking.unit_price_aed, Decimal('450.00'))
        self.assertEqual(booking.price_aed, Decimal('1350.00'))  # 450*3
        self.assertEqual(booking.deposit_aed, Decimal('200.00'))  # NOT multiplied
        self.assertEqual(booking.total_aed, Decimal('1550.00'))  # 1350+200

    def test_post_6_cars_tier_applied(self):
        """POST with quantity=6 uses 6+ tier (400 AED)."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '6',
        })
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 6)
        self.assertEqual(booking.unit_price_aed, Decimal('400.00'))
        self.assertEqual(booking.price_aed, Decimal('2400.00'))  # 400*6
        self.assertEqual(booking.total_aed, Decimal('2600.00'))  # 2400+200

    def test_post_quantity_exceeds_availability(self):
        """POST with quantity > available units shows no_availability."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '20',  # only 10 units exist
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'bookings/no_availability.html')
        self.assertEqual(Booking.objects.count(), 0)

    def test_post_invalid_quantity_defaults_to_1(self):
        """POST with invalid quantity falls back to 1."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': 'abc',
        })
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 1)

    def test_post_zero_quantity_defaults_to_1(self):
        """POST with quantity=0 is clamped to 1."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '0',
        })
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 1)

    def test_post_with_addons(self):
        """Addons are added once, not multiplied by quantity."""
        addon = AddonService.objects.create(
            service=self.service,
            name='Car wash',
            price_aed=Decimal('50.00'),
        )
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '3',
            'addons': [str(addon.id)],
        })
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 3)
        self.assertEqual(booking.addons_aed, Decimal('50.00'))
        # total = 1350 (450*3) + 50 (addon) + 200 (deposit) = 1600
        self.assertEqual(booking.total_aed, Decimal('1600.00'))

    def test_full_flow_pay_assigns_units(self):
        """Full flow: create booking → pay → units assigned."""
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '3',
        })
        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.booking_units.count(), 0)

        # Simulate payment
        booking.mark_as_paid('test_pay_123')
        booking.refresh_from_db()

        self.assertEqual(booking.status, Booking.Status.PAID)
        self.assertEqual(booking.booking_units.count(), 3)
        self.assertIsNotNone(booking.storage_unit)

        # 3 units unavailable, 7 still available
        self.assertEqual(
            StorageUnit.objects.filter(
                section=self.section, is_available=True
            ).count(),
            7
        )

    def test_full_flow_cancel_releases_units(self):
        """Full flow: create → pay → cancel → units released."""
        self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '3',
        })
        booking = Booking.objects.latest('created_at')
        booking.mark_as_paid('test_pay_456')

        self.assertEqual(
            StorageUnit.objects.filter(
                section=self.section, is_available=True
            ).count(),
            7
        )

        booking.cancel()

        # All 10 available again
        self.assertEqual(
            StorageUnit.objects.filter(
                section=self.section, is_available=True
            ).count(),
            10
        )

    def test_sequential_bookings_consume_units(self):
        """Two multi-car bookings correctly consume separate units."""
        # First booking: 3 cars
        self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '3',
        })
        b1 = Booking.objects.latest('created_at')
        b1.mark_as_paid('pay_1')

        # Second booking: 4 cars
        self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '4',
        })
        b2 = Booking.objects.latest('created_at')
        b2.mark_as_paid('pay_2')

        # 3 + 4 = 7 consumed, 3 left
        self.assertEqual(
            StorageUnit.objects.filter(
                section=self.section, is_available=True
            ).count(),
            3
        )

        # No overlapping units between bookings
        units_b1 = set(b1.booking_units.values_list('storage_unit_id', flat=True))
        units_b2 = set(b2.booking_units.values_list('storage_unit_id', flat=True))
        self.assertEqual(len(units_b1 & units_b2), 0)

    def test_booking_exhausts_units_then_fails(self):
        """After consuming all units, next booking shows no_availability."""
        # Book all 10 units
        self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '10',
        })
        b = Booking.objects.latest('created_at')
        b.mark_as_paid('pay_all')

        # Next booking should fail
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'quantity': '1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'bookings/no_availability.html')


class BookingExpirationTest(BookingTestMixin, TestCase):
    """Tests for 30-minute pending booking expiration."""

    def setUp(self):
        self.create_base_objects()

    def test_pending_booking_sets_expires_at(self):
        """New booking gets expires_at ~30 minutes from now."""
        before = timezone.now()
        booking = self.create_booking()
        after = timezone.now()
        self.assertGreaterEqual(booking.expires_at, before + timedelta(minutes=29))
        self.assertLessEqual(booking.expires_at, after + timedelta(minutes=31))

    def test_is_expired_false_when_fresh(self):
        booking = self.create_booking()
        self.assertFalse(booking.is_expired)

    def test_is_expired_true_after_30_minutes(self):
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])
        self.assertTrue(booking.is_expired)

    def test_cancel_expired_pending(self):
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])
        self.assertTrue(booking.is_expired)
        booking.cancel()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_mark_as_paid_rejects_expired_booking(self):
        """Cannot pay for an expired booking."""
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])

        result = booking.mark_as_paid('some_payment_id')

        self.assertFalse(result)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertIsNone(booking.paid_at)

    def test_mark_as_paid_works_when_not_expired(self):
        booking = self.create_booking()
        result = booking.mark_as_paid('valid_payment_id')
        self.assertTrue(result)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)
        self.assertIsNotNone(booking.paid_at)


class MockPaymentBlockedOnProdTest(BookingTestMixin, TestCase):
    """Mock payment must be blocked when Stripe is configured."""

    def setUp(self):
        self.create_base_objects()
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(STRIPE_SECRET_KEY='sk_live_test1234567890')
    def test_mock_payment_get_redirects_when_stripe_configured(self):
        booking = self.create_booking()
        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('cabinet', resp.url)

    @override_settings(STRIPE_SECRET_KEY='sk_live_test1234567890')
    def test_mock_payment_post_redirects_when_stripe_configured(self):
        booking = self.create_booking()
        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.post(url, {'action': 'pay'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('cabinet', resp.url)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    @override_settings(STRIPE_SECRET_KEY='')
    def test_mock_payment_works_without_stripe(self):
        booking = self.create_booking()
        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    @override_settings(STRIPE_SECRET_KEY='')
    def test_mock_payment_post_pays_without_stripe(self):
        booking = self.create_booking()
        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.post(url, {'action': 'pay'})
        self.assertEqual(resp.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)


class BookingCheckoutViewTest(BookingTestMixin, TestCase):
    """Tests for BookingCheckoutView."""

    def setUp(self):
        self.create_base_objects()
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(STRIPE_SECRET_KEY='')
    def test_checkout_redirects_to_mock_when_no_stripe(self):
        booking = self.create_booking()
        url = reverse('booking_checkout', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('mock-payment', resp.url)

    def test_checkout_cancels_expired_booking(self):
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])

        url = reverse('booking_checkout', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'bookings/cancelled.html')
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_checkout_rejects_other_users_booking(self):
        other_user = User.objects.create_user(
            email='other@example.com', password='pass123',
            first_name='Other', last_name='User',
        )
        booking = self.create_booking(user=other_user)
        url = reverse('booking_checkout', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class MockPaymentExpiredTest(BookingTestMixin, TestCase):
    """Mock payment rejects expired bookings."""

    def setUp(self):
        self.create_base_objects()
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(STRIPE_SECRET_KEY='')
    def test_mock_get_expired_booking_cancelled(self):
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])

        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'bookings/cancelled.html')
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    @override_settings(STRIPE_SECRET_KEY='')
    def test_mock_post_expired_booking_cancelled(self):
        booking = self.create_booking()
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=['expires_at'])

        url = reverse('booking_mock_payment', args=[booking.pk])
        resp = self.client.post(url, {'action': 'pay'})
        self.assertEqual(resp.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)


class DashboardPendingFilterTest(BookingTestMixin, TestCase):
    """Dashboard and billing views must not show expired pending bookings."""

    def setUp(self):
        self.create_base_objects()
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_hides_expired_pending(self):
        fresh = self.create_booking()
        expired = self.create_booking()
        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=['expires_at'])

        resp = self.client.get(reverse('cabinet-dashboard'))
        pending = list(resp.context['pending_bookings'])
        self.assertIn(fresh, pending)
        self.assertNotIn(expired, pending)

    def test_billing_hides_expired_pending(self):
        fresh = self.create_booking()
        expired = self.create_booking()
        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=['expires_at'])

        resp = self.client.get(reverse('cabinet-billing'))
        pending = list(resp.context['pending_payments'])
        self.assertIn(fresh, pending)
        self.assertNotIn(expired, pending)


class CancelExpiredBookingsCommandTest(BookingTestMixin, TestCase):
    """Tests for cancel_expired_bookings management command."""

    def setUp(self):
        self.create_base_objects()

    def test_cancels_expired_pending_bookings(self):
        from django.core.management import call_command

        expired = self.create_booking()
        expired.expires_at = timezone.now() - timedelta(minutes=5)
        expired.save(update_fields=['expires_at'])

        fresh = self.create_booking()

        call_command('cancel_expired_bookings')

        expired.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(expired.status, Booking.Status.CANCELLED)
        self.assertEqual(fresh.status, Booking.Status.PENDING)

    def test_dry_run_does_not_cancel(self):
        from django.core.management import call_command

        expired = self.create_booking()
        expired.expires_at = timezone.now() - timedelta(minutes=5)
        expired.save(update_fields=['expires_at'])

        call_command('cancel_expired_bookings', '--dry-run')

        expired.refresh_from_db()
        self.assertEqual(expired.status, Booking.Status.PENDING)

    def test_does_not_touch_paid_bookings(self):
        from django.core.management import call_command

        booking = self.create_booking()
        booking.mark_as_paid('test_pay')
        booking.refresh_from_db()

        call_command('cancel_expired_bookings')

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)


class MarkAsPaidAtomicityTest(BookingTestMixin, TestCase):
    """Tests for atomic mark_as_paid and double-payment prevention."""

    def setUp(self):
        self.create_base_objects()

    def test_mark_as_paid_only_works_once(self):
        """Second call to mark_as_paid returns False (already paid)."""
        booking = self.create_booking()
        result1 = booking.mark_as_paid('payment_1')
        self.assertTrue(result1)

        booking2 = Booking.objects.get(pk=booking.pk)
        result2 = booking2.mark_as_paid('payment_2')
        self.assertFalse(result2)

        booking.refresh_from_db()
        self.assertEqual(booking.stripe_payment_id, 'payment_1')

    def test_mark_as_paid_rejects_non_pending(self):
        """Cannot pay a cancelled booking."""
        booking = self.create_booking()
        booking.cancel()

        result = booking.mark_as_paid('payment_after_cancel')
        self.assertFalse(result)

    def test_mark_as_paid_stores_receipt_url(self):
        booking = self.create_booking()
        booking.mark_as_paid('pi_test', receipt_url='https://receipt.stripe.com/test')
        booking.refresh_from_db()
        self.assertEqual(booking.stripe_receipt_url, 'https://receipt.stripe.com/test')

    def test_concurrent_bookings_no_unit_overlap(self):
        """Two bookings paid sequentially cannot share units."""
        b1 = self.create_booking(quantity=5)
        b2 = self.create_booking(quantity=5)

        b1.mark_as_paid('pay_1')
        b2.mark_as_paid('pay_2')

        units_b1 = set(b1.booking_units.values_list('storage_unit_id', flat=True))
        units_b2 = set(b2.booking_units.values_list('storage_unit_id', flat=True))
        self.assertEqual(len(units_b1), 5)
        self.assertEqual(len(units_b2), 5)
        self.assertEqual(len(units_b1 & units_b2), 0)

    def test_no_units_left_after_full_booking(self):
        """After booking all 10 units, next booking fails to assign."""
        b1 = self.create_booking(quantity=10)
        b1.mark_as_paid('pay_full')

        b2 = self.create_booking(quantity=1)
        b2.mark_as_paid('pay_extra')
        b2.refresh_from_db()
        # Should be paid but no units assigned
        self.assertEqual(b2.booking_units.count(), 0)


class BookingLifecycleTest(BookingTestMixin, TestCase):
    """Tests for activate/expire/complete lifecycle methods."""

    def setUp(self):
        self.create_base_objects()

    def test_activate_paid_booking(self):
        booking = self.create_booking(
            start_date=timezone.now().date(),
        )
        booking.mark_as_paid('pay_activate')
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)

        booking.activate()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACTIVE)

    def test_activate_ignores_future_start(self):
        booking = self.create_booking(
            start_date=timezone.now().date() + timedelta(days=7),
        )
        booking.status = Booking.Status.PAID
        booking.save(update_fields=['status'])

        booking.activate()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)

    def test_expire_active_booking(self):
        booking = self.create_booking()
        booking.status = Booking.Status.ACTIVE
        booking.end_date = timezone.now().date() - timedelta(days=1)
        booking.save(update_fields=['status', 'end_date'])

        booking.expire()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.EXPIRED)

    def test_expire_does_not_release_units(self):
        """Expired booking keeps units occupied until force release."""
        booking = self.create_booking(quantity=2)
        booking.mark_as_paid('pay_expire')
        booking.refresh_from_db()
        booking.status = Booking.Status.ACTIVE
        booking.save(update_fields=['status'])
        booking.expire()

        # Units should still be unavailable
        for bu in booking.booking_units.all():
            self.assertFalse(
                StorageUnit.objects.get(pk=bu.storage_unit_id).is_available
            )

    def test_complete_releases_units(self):
        """Force release (complete) frees units."""
        booking = self.create_booking(quantity=2)
        booking.mark_as_paid('pay_complete')
        booking.refresh_from_db()
        booking.status = Booking.Status.ACTIVE
        booking.save(update_fields=['status'])
        booking.complete()

        for bu in booking.booking_units.all():
            self.assertTrue(
                StorageUnit.objects.get(pk=bu.storage_unit_id).is_available
            )
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_extension_mark_as_paid(self):
        """Extension updates parent end_date and marks itself completed."""
        parent = self.create_booking()
        parent.mark_as_paid('pay_parent')
        parent.refresh_from_db()
        original_end = parent.end_date

        extension = self.create_booking(
            parent_booking=parent,
            start_date=original_end,
            end_date=original_end + timedelta(days=30),
        )
        extension.mark_as_paid('pay_ext')
        extension.refresh_from_db()
        parent.refresh_from_db()

        self.assertEqual(extension.status, Booking.Status.COMPLETED)
        self.assertEqual(parent.end_date, original_end + timedelta(days=30))


class UpdateBookingStatusesCommandTest(BookingTestMixin, TestCase):
    """Tests for update_booking_statuses management command."""

    def setUp(self):
        self.create_base_objects()

    def test_activates_paid_booking_on_start_date(self):
        from django.core.management import call_command

        booking = self.create_booking(start_date=timezone.now().date())
        booking.status = Booking.Status.PAID
        booking.save(update_fields=['status'])

        call_command('update_booking_statuses')

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACTIVE)

    def test_expires_active_booking_past_end_date(self):
        from django.core.management import call_command

        booking = self.create_booking()
        booking.status = Booking.Status.ACTIVE
        booking.end_date = timezone.now().date() - timedelta(days=1)
        booking.save(update_fields=['status', 'end_date'])

        call_command('update_booking_statuses')

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.EXPIRED)

    def test_does_not_activate_future_booking(self):
        from django.core.management import call_command

        booking = self.create_booking(
            start_date=timezone.now().date() + timedelta(days=5),
        )
        booking.status = Booking.Status.PAID
        booking.save(update_fields=['status'])

        call_command('update_booking_statuses')

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)
