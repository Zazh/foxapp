from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User
from policies.models import Policy, PolicyConsent
from services.models import (
    Service, Tariff, TariffPeriod, TariffPriceTier,
    Section, StorageUnit,
)
from locations.models import Location


class PolicyModelTest(TestCase):

    def test_create_policy(self):
        p = Policy.objects.create(title='Privacy Policy', slug='privacy', content='<p>Text</p>')
        self.assertEqual(str(p), 'Privacy Policy')

    def test_get_absolute_url(self):
        p = Policy.objects.create(title='Privacy', slug='privacy', content='')
        self.assertEqual(p.get_absolute_url(), '/policy/privacy/')

    def test_ordering_by_sort_order(self):
        p1 = Policy.objects.create(title='B', slug='b', content='', sort_order=2)
        p2 = Policy.objects.create(title='A', slug='a', content='', sort_order=1)
        policies = list(Policy.objects.all())
        self.assertEqual(policies[0], p2)
        self.assertEqual(policies[1], p1)

    def test_slug_unique(self):
        Policy.objects.create(title='A', slug='test', content='')
        with self.assertRaises(Exception):
            Policy.objects.create(title='B', slug='test', content='')


class PolicyDetailViewTest(TestCase):

    def test_active_policy_visible(self):
        Policy.objects.create(title='Privacy', slug='privacy', content='<p>Content</p>', is_active=True)
        resp = self.client.get(reverse('policy_detail', kwargs={'slug': 'privacy'}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Privacy')
        self.assertContains(resp, '<p>Content</p>')

    def test_inactive_policy_404(self):
        Policy.objects.create(title='Old', slug='old', content='', is_active=False)
        resp = self.client.get(reverse('policy_detail', kwargs={'slug': 'old'}))
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_slug_404(self):
        resp = self.client.get(reverse('policy_detail', kwargs={'slug': 'nope'}))
        self.assertEqual(resp.status_code, 404)


class PolicyConsentModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='pass123',
            first_name='Test', last_name='User',
        )

    def test_consent_creation(self):
        p = Policy.objects.create(title='Terms', slug='terms', content='')
        consent = PolicyConsent.objects.create(
            user=self.user, policy=p, ip_address='127.0.0.1'
        )
        self.assertEqual(str(consent), 'test@example.com — Terms')

    def test_unique_user_policy(self):
        p = Policy.objects.create(title='Terms', slug='terms', content='')
        PolicyConsent.objects.create(user=self.user, policy=p)
        with self.assertRaises(Exception):
            PolicyConsent.objects.create(user=self.user, policy=p)


class BookingPolicyValidationTest(TestCase):
    """Integration: BookingCreateView rejects without policy acceptance."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='pass123',
            first_name='Test', last_name='User',
        )
        self.service = Service.objects.create(
            service_type=Service.ServiceType.AUTO,
            name='Auto Storage',
        )
        self.location = Location.objects.create(
            name='Dubai',
            location_type=Location.LocationType.AUTO_STORAGE,
            street='Test St', building='1',
            latitude=Decimal('25.0'), longitude=Decimal('55.0'),
        )
        self.tariff = Tariff.objects.create(
            service=self.service, location=self.location,
            name='Standard', name_en='Standard',
            deposit_aed=Decimal('200.00'),
        )
        self.period = TariffPeriod.objects.create(
            tariff=self.tariff, name='1 Month', name_en='1 Month',
            duration_type=TariffPeriod.DurationType.MONTHS,
            duration_value=1,
        )
        TariffPriceTier.objects.create(
            period=self.period, min_units=1, max_units=None,
            price_per_unit_aed=Decimal('500.00'),
        )
        self.section = Section.objects.create(
            location=self.location, service=self.service, name='A',
        )
        for i in range(5):
            StorageUnit.objects.create(section=self.section, unit_number=f'{i+1:02d}')

        self.policy = Policy.objects.create(
            title='Terms', slug='terms', content='<p>Terms</p>',
            is_required=True, is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('booking_create', kwargs={
            'service_type': 'auto', 'slug': self.tariff.slug,
        })

    def test_booking_rejected_without_policy(self):
        resp = self.client.post(self.url, {'period': self.period.id})
        # Should redirect back (not create booking)
        self.assertEqual(resp.status_code, 302)
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 0)

    def test_booking_proceeds_with_policy(self):
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'accepted_policies': [str(self.policy.id)],
        })
        self.assertEqual(resp.status_code, 302)
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 1)

    def test_consent_recorded(self):
        self.client.post(self.url, {
            'period': self.period.id,
            'accepted_policies': [str(self.policy.id)],
        })
        self.assertTrue(
            PolicyConsent.objects.filter(user=self.user, policy=self.policy).exists()
        )

    def test_multiple_policies_all_required(self):
        p2 = Policy.objects.create(
            title='Privacy', slug='privacy', content='',
            is_required=True, is_active=True,
        )
        # Only accept one of two
        resp = self.client.post(self.url, {
            'period': self.period.id,
            'accepted_policies': [str(self.policy.id)],
        })
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 0)

        # Accept both
        self.client.post(self.url, {
            'period': self.period.id,
            'accepted_policies': [str(self.policy.id), str(p2.id)],
        })
        self.assertEqual(Booking.objects.count(), 1)

    def test_no_required_policies_booking_works(self):
        """When no required policies exist, booking proceeds normally."""
        self.policy.is_required = False
        self.policy.save()
        resp = self.client.post(self.url, {'period': self.period.id})
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 1)

    def test_inactive_required_policy_ignored(self):
        """Inactive required policy should not block booking."""
        self.policy.is_active = False
        self.policy.save()
        resp = self.client.post(self.url, {'period': self.period.id})
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 1)

    def test_already_accepted_policy_not_required_again(self):
        """User who already accepted a policy can book without re-accepting."""
        PolicyConsent.objects.create(
            user=self.user, policy=self.policy, ip_address='127.0.0.1'
        )
        # No accepted_policies in POST — should still work
        resp = self.client.post(self.url, {'period': self.period.id})
        from bookings.models import Booking
        self.assertEqual(Booking.objects.count(), 1)

    def test_tariff_page_hides_accepted_policies(self):
        """Tariff detail page should not show already-accepted policies."""
        PolicyConsent.objects.create(
            user=self.user, policy=self.policy, ip_address='127.0.0.1'
        )
        tariff_url = reverse('tariff_detail', kwargs={
            'service_type': 'auto', 'slug': self.tariff.slug,
        })
        resp = self.client.get(tariff_url)
        self.assertNotContains(resp, 'policy-checkbox')

    def test_consent_label_used_in_template(self):
        """Custom consent_label with {link} placeholder renders correctly."""
        self.policy.consent_label = 'I agree to the {link} fully'
        self.policy.save()
        tariff_url = reverse('tariff_detail', kwargs={
            'service_type': 'auto', 'slug': self.tariff.slug,
        })
        resp = self.client.get(tariff_url)
        self.assertContains(resp, 'I agree to the')
        self.assertContains(resp, 'fully')
        self.assertContains(resp, f'/policy/{self.policy.slug}/')


class FooterPoliciesTest(TestCase):

    def test_footer_shows_active_policies(self):
        Policy.objects.create(title='Privacy', slug='privacy', content='', is_active=True)
        Policy.objects.create(title='Hidden', slug='hidden', content='', is_active=False)
        resp = self.client.get(reverse('home'))
        self.assertContains(resp, 'Privacy')
        self.assertNotContains(resp, 'Hidden')
