from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking
from services.models import (
    Service, Tariff, TariffPeriod, TariffPriceTier, Section, StorageUnit,
)
from locations.models import Location


class ManagerFlowTestMixin:
    """Shared setup for manager backoffice tests."""

    def create_base(self):
        self.manager = User.objects.create_user(
            email='manager@foxbox.ae', password='managerpass123',
            first_name='Manager', last_name='User',
        )
        self.manager.is_staff = True
        self.manager.save(update_fields=['is_staff'])

        self.service = Service.objects.create(
            service_type=Service.ServiceType.AUTO, name='Auto Storage',
        )
        self.location = Location.objects.create(
            name='Dubai', location_type=Location.LocationType.AUTO_STORAGE,
            street='Test Street', building='1',
            latitude=Decimal('25.0000000'), longitude=Decimal('55.0000000'),
        )
        self.tariff = Tariff.objects.create(
            service=self.service, location=self.location,
            name='VIP Parking', name_en='VIP Parking',
            deposit_aed=Decimal('200.00'),
        )
        self.period = TariffPeriod.objects.create(
            tariff=self.tariff, name='1 Month', name_en='1 Month',
            duration_type=TariffPeriod.DurationType.MONTHS, duration_value=1,
        )
        TariffPriceTier.objects.create(
            period=self.period, min_units=1, max_units=None,
            price_per_unit_aed=Decimal('500.00'),
        )
        self.section = Section.objects.create(
            location=self.location, service=self.service, name='A',
        )
        self.units = []
        for i in range(1, 6):
            unit = StorageUnit.objects.create(
                section=self.section, unit_number=f'{i:02d}',
            )
            self.units.append(unit)

        self.client = Client()
        self.client.force_login(self.manager)


class ManagerUserCreateViewTest(ManagerFlowTestMixin, TestCase):
    """Менеджер создаёт клиента через бэкофис."""

    def setUp(self):
        self.create_base()

    def test_get_renders_form(self):
        resp = self.client.get(reverse('backoffice:user_create'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Email')
        self.assertContains(resp, 'Password')

    def test_post_creates_email_user(self):
        resp = self.client.post(reverse('backoffice:user_create'), {
            'email': 'newcust@example.com',
            'first_name': 'Customer',
            'last_name': 'Test',
            'phone': '+971500000000',
            'password': 'StrongPass123!',
        })
        self.assertEqual(resp.status_code, 302)

        user = User.objects.get(email='newcust@example.com')
        self.assertEqual(user.auth_provider, 'email')
        self.assertTrue(user.is_verified)
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            email='exists@example.com', password='p123456789',
            first_name='X', last_name='Y',
        )
        resp = self.client.post(reverse('backoffice:user_create'), {
            'email': 'exists@example.com',
            'first_name': 'New',
            'password': 'StrongPass123!',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'already exists')

    def test_weak_password_rejected(self):
        resp = self.client.post(reverse('backoffice:user_create'), {
            'email': 'weak@example.com',
            'first_name': 'Weak',
            'password': '123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors.get('password'))

    def test_then_create_booking_redirect(self):
        resp = self.client.post(reverse('backoffice:user_create'), {
            'email': 'next@example.com',
            'first_name': 'Next',
            'password': 'StrongPass123!',
            'then': 'create_booking',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/backoffice/bookings/create/?user=', resp.url)

    def test_requires_staff(self):
        non_staff = User.objects.create_user(
            email='nonstaff@x.com', password='p123456789',
            first_name='N', last_name='S',
        )
        client = Client()
        client.force_login(non_staff)
        resp = client.get(reverse('backoffice:user_create'))
        self.assertNotEqual(resp.status_code, 200)


class ManagerBookingCreateViewTest(ManagerFlowTestMixin, TestCase):
    """Менеджер создаёт бронирование через бэкофис."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='cust@example.com', password='p123456789',
            first_name='Cust', last_name='Omer',
        )

    def _post(self, **overrides):
        data = {
            'user_id': self.customer.pk,
            'tariff': self.tariff.pk,
            'period_type': 'standard',
            'period': self.period.pk,
            'quantity': 1,
            'payment_method': Booking.PaymentMethod.LK_INVOICE,
        }
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post(reverse('backoffice:booking_create'), data)

    def test_get_renders_form(self):
        resp = self.client.get(reverse('backoffice:booking_create'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Payment method')

    def test_lk_invoice_creates_pending_booking(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.user, self.customer)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.payment_method, Booking.PaymentMethod.LK_INVOICE)
        self.assertEqual(booking.created_by_manager, self.manager)
        self.assertEqual(booking.deposit_aed, Decimal('0'))
        self.assertEqual(booking.total_aed, Decimal('500.00'))
        self.assertEqual(booking.booking_units.count(), 0)

    def test_cash_activates_immediately(self):
        resp = self._post(
            payment_method=Booking.PaymentMethod.CASH,
        )
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.status, Booking.Status.PAID)
        self.assertEqual(booking.payment_method, Booking.PaymentMethod.CASH)
        # amount_collected = total_aed (single price source)
        self.assertEqual(booking.payment_amount_collected, booking.total_aed)
        self.assertEqual(booking.booking_units.count(), 1)
        self.assertIsNotNone(booking.paid_at)

    def test_stripe_payment_link_activates_immediately(self):
        resp = self._post(
            payment_method=Booking.PaymentMethod.STRIPE_PAYMENT_LINK,
        )
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.status, Booking.Status.PAID)
        self.assertEqual(booking.payment_method, Booking.PaymentMethod.STRIPE_PAYMENT_LINK)
        self.assertEqual(booking.payment_amount_collected, booking.total_aed)
        self.assertEqual(booking.booking_units.count(), 1)

    def test_specific_unit_assigned(self):
        target = self.units[2]
        resp = self._post(
            payment_method=Booking.PaymentMethod.CASH,
            storage_unit=target.pk,
        )
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.storage_unit_id, target.pk)
        for unit in self.units:
            unit.refresh_from_db()
        self.assertFalse(self.units[2].is_available)
        self.assertTrue(self.units[0].is_available)

    def test_custom_dates_and_price(self):
        start = timezone.now().date() + timedelta(days=2)
        end = start + timedelta(days=10)
        resp = self._post(
            period_type='custom',
            period=None,
            payment_method=Booking.PaymentMethod.CASH,
            custom_start_date=start.isoformat(),
            custom_end_date=end.isoformat(),
            price_aed='250.00',
        )
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.start_date, start)
        self.assertEqual(booking.end_date, end)
        self.assertEqual(booking.price_aed, Decimal('250.00'))
        self.assertEqual(booking.payment_amount_collected, Decimal('250.00'))

    def test_custom_dates_without_price_rejected(self):
        start = timezone.now().date() + timedelta(days=2)
        end = start + timedelta(days=10)
        resp = self._post(
            period_type='custom',
            period=None,
            custom_start_date=start.isoformat(),
            custom_end_date=end.isoformat(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors.get('price_aed'))

    def test_standard_without_period_rejected(self):
        resp = self._post(period=None)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors.get('period'))

    def test_override_price_in_standard_mode(self):
        resp = self._post(
            payment_method=Booking.PaymentMethod.CASH,
            override_price='on',
            price_aed='350.00',
        )
        self.assertEqual(resp.status_code, 302)
        booking = Booking.objects.latest('created_at')
        # Standard period would be 500, but override forces 350
        self.assertEqual(booking.price_aed, Decimal('350.00'))
        # amount_collected mirrors total_aed (= price_aed since deposit=0)
        self.assertEqual(booking.payment_amount_collected, Decimal('350.00'))

    def test_quantity_exceeding_availability_rejected(self):
        """quantity > available_units → ошибка валидации с фактическим числом."""
        # У нас 5 юнитов в self.units (см. ManagerFlowTestMixin)
        resp = self._post(
            quantity=10,
            payment_method=Booking.PaymentMethod.CASH,
        )
        self.assertEqual(resp.status_code, 200)
        errors = resp.context['form'].errors.get('quantity', [])
        self.assertTrue(errors)
        self.assertIn('5', str(errors))  # сообщение содержит фактическое число

    def test_specific_unit_with_multi_quantity_rejected(self):
        """quantity > 1 + конкретный юнит → ошибка валидации."""
        resp = self._post(
            quantity=3,
            storage_unit=self.units[0].pk,
            payment_method=Booking.PaymentMethod.CASH,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors.get('storage_unit'))

    def test_quantity_uses_tier_price(self):
        TariffPriceTier.objects.create(
            period=self.period, min_units=2, max_units=None,
            price_per_unit_aed=Decimal('400.00'),
        )
        default = self.period.price_tiers.get(min_units=1)
        default.max_units = 1
        default.save()

        resp = self._post(
            quantity=3,
            payment_method=Booking.PaymentMethod.CASH,
            payment_amount_collected='1200.00',
        )
        self.assertEqual(resp.status_code, 302)

        booking = Booking.objects.latest('created_at')
        self.assertEqual(booking.quantity, 3)
        self.assertEqual(booking.unit_price_aed, Decimal('400.00'))
        self.assertEqual(booking.price_aed, Decimal('1200.00'))
        self.assertEqual(booking.booking_units.count(), 3)

    def test_initial_user_from_query_param(self):
        resp = self.client.get(
            reverse('backoffice:booking_create') + f'?user={self.customer.pk}'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            str(resp.context['form'].initial.get('user_id')),
            str(self.customer.pk),
        )
        # Preselected user data should be passed to the JS
        self.assertEqual(resp.context['preselected_user']['id'], self.customer.pk)


class BackofficeApiTest(ManagerFlowTestMixin, TestCase):
    """Tests for the autocomplete + inline-create AJAX endpoints."""

    def setUp(self):
        self.create_base()

    def test_user_search_returns_matches(self):
        User.objects.create_user(
            email='alice@example.com', password='p123456789',
            first_name='Alice', last_name='Wonder', phone='+971500000001',
        )
        User.objects.create_user(
            email='bob@example.com', password='p123456789',
            first_name='Bob', last_name='Builder', phone='+971500000002',
        )

        resp = self.client.get(reverse('backoffice:api_user_search') + '?q=alice')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        emails = [u['email'] for u in data['results']]
        self.assertIn('alice@example.com', emails)
        self.assertNotIn('bob@example.com', emails)

    def test_user_search_short_query_empty(self):
        resp = self.client.get(reverse('backoffice:api_user_search') + '?q=a')
        self.assertEqual(resp.json(), {'results': []})

    def test_user_search_by_phone(self):
        User.objects.create_user(
            email='phone@example.com', password='p123456789',
            first_name='Phone', last_name='User', phone='+971501234567',
        )
        resp = self.client.get(reverse('backoffice:api_user_search') + '?q=12345')
        emails = [u['email'] for u in resp.json()['results']]
        self.assertIn('phone@example.com', emails)

    def test_user_create_via_api(self):
        resp = self.client.post(reverse('backoffice:api_user_create'), {
            'email': 'inline@example.com',
            'first_name': 'Inline',
            'password': 'StrongPass123!',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['email'], 'inline@example.com')
        self.assertTrue(User.objects.filter(email='inline@example.com').exists())

    def test_user_create_validation_errors(self):
        resp = self.client.post(reverse('backoffice:api_user_create'), {
            'email': 'bad',
            'first_name': '',
            'password': '123',
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('email', data['errors'])
        self.assertIn('first_name', data['errors'])
        self.assertIn('password', data['errors'])

    def test_tariff_info_returns_periods(self):
        resp = self.client.get(reverse('backoffice:api_tariff_info', args=[self.tariff.pk]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['id'], self.tariff.pk)
        self.assertEqual(data['available_units'], 5)
        self.assertEqual(len(data['periods']), 1)
        self.assertEqual(data['periods'][0]['base_price'], '500.00')

    def test_api_requires_staff(self):
        non_staff = User.objects.create_user(
            email='ns@x.com', password='p123456789',
            first_name='N', last_name='S',
        )
        client = Client()
        client.force_login(non_staff)
        resp = client.get(reverse('backoffice:api_user_search') + '?q=test')
        self.assertNotEqual(resp.status_code, 200)


class UnitReleaseActionTest(ManagerFlowTestMixin, TestCase):
    """Action 'release' в unit_toggle_status должен идти через booking.complete()."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='cust2@example.com', password='p123456789',
            first_name='C', last_name='Two',
        )

    def _release(self, unit_pk):
        return self.client.post(
            reverse('backoffice:unit_toggle', args=[unit_pk]),
            {'action': 'release'},
        )

    def _create_paid_booking_on_unit(self, unit):
        booking = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date(),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            payment_method=Booking.PaymentMethod.CASH,
        )
        booking.activate_externally_paid(Decimal('500.00'), storage_unit=unit)
        booking.refresh_from_db()
        return booking

    def test_release_completes_active_booking(self):
        """Release с PAID-бронью → complete() и юнит свободен."""
        unit = self.units[0]
        booking = self._create_paid_booking_on_unit(unit)
        self.assertEqual(booking.status, Booking.Status.PAID)

        resp = self._release(unit.pk)
        self.assertEqual(resp.status_code, 302)

        booking.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.assertTrue(unit.is_available)

    def test_release_orphan_flag_without_booking(self):
        """Release на юните is_available=False без PAID-брони — просто чистит флаг."""
        unit = self.units[0]
        unit.is_available = False
        unit.save(update_fields=['is_available'])

        resp = self._release(unit.pk)
        self.assertEqual(resp.status_code, 302)

        unit.refresh_from_db()
        self.assertTrue(unit.is_available)

    def test_release_does_not_touch_extension(self):
        """Если на юните висит parent + extension PENDING, release завершит parent (extension не трогаем — это PENDING)."""
        unit = self.units[0]
        parent = self._create_paid_booking_on_unit(unit)

        # PENDING extension
        ext = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            storage_unit=unit,
            start_date=parent.end_date,
            end_date=parent.end_date + timedelta(days=30),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            parent_booking=parent,
        )

        self._release(unit.pk)
        parent.refresh_from_db()
        ext.refresh_from_db()
        self.assertEqual(parent.status, Booking.Status.COMPLETED)
        # Extension остаётся PENDING — release не должен его кантовать
        self.assertEqual(ext.status, Booking.Status.PENDING)


class ManagerSetPasswordTest(ManagerFlowTestMixin, TestCase):
    """Менеджер сбрасывает пароль клиента из бэкофиса."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='reset@example.com', password='OldPass1234',
            first_name='Reset', last_name='Me',
        )

    def _url(self, pk=None):
        return reverse('backoffice:user_set_password', args=[pk or self.customer.pk])

    def test_set_new_password_success(self):
        resp = self.client.post(self._url(), {'password': 'BrandNew2026!'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password('BrandNew2026!'))
        self.assertFalse(self.customer.check_password('OldPass1234'))

    def test_empty_password_rejected(self):
        resp = self.client.post(self._url(), {'password': ''})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('required', data['error'].lower())

    def test_weak_password_rejected(self):
        resp = self.client.post(self._url(), {'password': '123'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        # Original password unchanged
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password('OldPass1234'))

    def test_get_method_not_allowed(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_requires_staff(self):
        non_staff = User.objects.create_user(
            email='regular@x.com', password='p123456789',
            first_name='R', last_name='U',
        )
        client = Client()
        client.force_login(non_staff)
        resp = client.post(self._url(), {'password': 'NewPass2026!'})
        self.assertNotEqual(resp.status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.check_password('NewPass2026!'))

    def test_cannot_change_superuser_password_as_staff(self):
        admin = User.objects.create_user(
            email='admin@x.com', password='SuperPass1234',
            first_name='Admin', last_name='X',
        )
        admin.is_superuser = True
        admin.save(update_fields=['is_superuser'])

        resp = self.client.post(self._url(pk=admin.pk), {'password': 'Hijack2026!'})
        self.assertEqual(resp.status_code, 403)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password('SuperPass1234'))


class ExtensionViaCreateFormTest(ManagerFlowTestMixin, TestCase):
    """Менеджерская форма создания брони превращается в extension,
    если выбран юнит, который уже принадлежит этому клиенту."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='ext@example.com', password='p123456789',
            first_name='Ext', last_name='Customer',
        )
        # Создаём активную бронь — оплачена, юнит занят
        self.parent = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date() - timedelta(days=10),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            payment_method=Booking.PaymentMethod.CASH,
        )
        self.parent.activate_externally_paid(Decimal('500.00'), storage_unit=self.units[0])
        self.parent.refresh_from_db()

    def _post(self, **overrides):
        data = {
            'user_id': self.customer.pk,
            'tariff': self.tariff.pk,
            'period_type': 'standard',
            'period': self.period.pk,
            'quantity': 1,
            'payment_method': Booking.PaymentMethod.LK_INVOICE,
            'storage_unit': self.units[0].pk,  # Same unit as parent → extension
        }
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post(reverse('backoffice:booking_create'), data)

    def test_api_returns_active_booking(self):
        resp = self.client.get(
            reverse('backoffice:api_user_active_booking', args=[self.customer.pk])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['active_booking']
        self.assertEqual(data['id'], self.parent.pk)
        self.assertEqual(data['unit_id'], self.units[0].pk)
        self.assertEqual(data['number'], self.parent.number)

    def test_api_returns_null_when_no_active_booking(self):
        new_user = User.objects.create_user(
            email='nobookings@x.com', password='p1', first_name='N', last_name='B',
        )
        resp = self.client.get(
            reverse('backoffice:api_user_active_booking', args=[new_user.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['active_booking'])

    def test_selecting_own_unit_creates_extension_lk_invoice(self):
        original_end = self.parent.end_date
        resp = self._post(payment_method=Booking.PaymentMethod.LK_INVOICE)
        self.assertEqual(resp.status_code, 302)

        ext = Booking.objects.exclude(pk=self.parent.pk).latest('created_at')
        self.assertEqual(ext.parent_booking_id, self.parent.pk)
        self.assertEqual(ext.start_date, original_end)
        self.assertEqual(ext.deposit_aed, Decimal('0'))
        self.assertEqual(ext.status, Booking.Status.PENDING)
        # Same unit
        self.assertEqual(ext.storage_unit_id, self.units[0].pk)

    def test_selecting_own_unit_creates_extension_cash(self):
        original_end = self.parent.end_date
        resp = self._post(payment_method=Booking.PaymentMethod.CASH)
        self.assertEqual(resp.status_code, 302)

        ext = Booking.objects.exclude(pk=self.parent.pk).latest('created_at')
        self.assertEqual(ext.parent_booking_id, self.parent.pk)
        # Cash extension is immediately COMPLETED
        self.assertEqual(ext.status, Booking.Status.COMPLETED)
        self.assertEqual(ext.payment_amount_collected, ext.total_aed)
        # Parent end_date got pushed
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.end_date, ext.end_date)
        self.assertGreater(self.parent.end_date, original_end)

    def test_selecting_own_unit_creates_extension_stripe_link(self):
        resp = self._post(payment_method=Booking.PaymentMethod.STRIPE_PAYMENT_LINK)
        self.assertEqual(resp.status_code, 302)

        ext = Booking.objects.exclude(pk=self.parent.pk).latest('created_at')
        self.assertEqual(ext.parent_booking_id, self.parent.pk)
        self.assertEqual(ext.status, Booking.Status.COMPLETED)

    def test_extension_does_not_consume_extra_unit(self):
        """Extension использует тот же юнит — никаких дополнительных юнитов."""
        self.units[0].refresh_from_db()
        self.assertFalse(self.units[0].is_available)  # Already occupied by parent

        self._post(payment_method=Booking.PaymentMethod.CASH)

        self.units[0].refresh_from_db()
        self.assertFalse(self.units[0].is_available)  # Still occupied
        # Other units still free
        self.units[1].refresh_from_db()
        self.assertTrue(self.units[1].is_available)

    def test_extension_with_custom_dates(self):
        from datetime import date
        new_end = self.parent.end_date + timedelta(days=15)
        resp = self._post(
            period_type='custom',
            period=None,
            payment_method=Booking.PaymentMethod.CASH,
            custom_start_date=self.parent.end_date.isoformat(),
            custom_end_date=new_end.isoformat(),
            price_aed='200.00',
        )
        self.assertEqual(resp.status_code, 302)

        ext = Booking.objects.exclude(pk=self.parent.pk).latest('created_at')
        self.assertEqual(ext.parent_booking_id, self.parent.pk)
        self.assertEqual(ext.end_date, new_end)
        self.assertEqual(ext.price_aed, Decimal('200.00'))
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.end_date, new_end)

    def test_selecting_other_customers_unit_rejected(self):
        # Другой клиент пытается забронировать юнит первого
        another = User.objects.create_user(
            email='another@x.com', password='p1', first_name='A', last_name='N',
        )
        resp = self.client.post(reverse('backoffice:booking_create'), {
            'user_id': another.pk,
            'tariff': self.tariff.pk,
            'period_type': 'standard',
            'period': self.period.pk,
            'quantity': 1,
            'payment_method': Booking.PaymentMethod.CASH,
            'storage_unit': self.units[0].pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors.get('storage_unit'))

    def test_selecting_free_unit_creates_new_booking_not_extension(self):
        """Авто или free unit → новая бронь, а не extension."""
        resp = self._post(
            storage_unit=self.units[2].pk,  # Free unit
            payment_method=Booking.PaymentMethod.CASH,
        )
        self.assertEqual(resp.status_code, 302)

        new_booking = Booking.objects.exclude(pk=self.parent.pk).latest('created_at')
        self.assertIsNone(new_booking.parent_booking_id)
        self.assertEqual(new_booking.storage_unit_id, self.units[2].pk)


class CompleteExtensionExternallyPaidTest(ManagerFlowTestMixin, TestCase):
    """Direct tests for Booking.complete_extension_externally_paid."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='cext@example.com', password='p1', first_name='C', last_name='E',
        )
        self.parent = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date() - timedelta(days=5),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
        )
        self.parent.mark_as_paid('pi_p')
        self.parent.refresh_from_db()

    def test_completes_extension_and_pushes_parent_end_date(self):
        new_end = self.parent.end_date + timedelta(days=30)
        ext = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            storage_unit=self.parent.storage_unit,
            start_date=self.parent.end_date,
            end_date=new_end,
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            payment_method=Booking.PaymentMethod.CASH,
            parent_booking=self.parent,
        )

        ok = ext.complete_extension_externally_paid(Decimal('500.00'))
        self.assertTrue(ok)

        ext.refresh_from_db()
        self.parent.refresh_from_db()
        self.assertEqual(ext.status, Booking.Status.COMPLETED)
        self.assertEqual(ext.payment_amount_collected, Decimal('500.00'))
        self.assertEqual(self.parent.end_date, new_end)

    def test_revives_expired_parent_to_active(self):
        """complete_extension_externally_paid обновляет parent.end_date.

        В новой модели parent остаётся PAID (никаких ACTIVE/EXPIRED статусов).
        Active vs overdue derivable через display_status / is_overdue.
        """
        # Имитируем истёкший parent (end_date в прошлом, status остаётся PAID)
        self.parent.end_date = timezone.now().date() - timedelta(days=2)
        self.parent.save(update_fields=['end_date'])
        self.assertTrue(self.parent.is_overdue)

        future_end = timezone.now().date() + timedelta(days=30)
        ext = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            storage_unit=self.parent.storage_unit,
            start_date=self.parent.end_date,
            end_date=future_end,
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            payment_method=Booking.PaymentMethod.CASH,
            parent_booking=self.parent,
        )
        ext.complete_extension_externally_paid(Decimal('500.00'))

        self.parent.refresh_from_db()
        # Status PAID не меняется; is_overdue теперь False; is_active=True
        self.assertEqual(self.parent.status, Booking.Status.PAID)
        self.assertEqual(self.parent.end_date, future_end)
        self.assertFalse(self.parent.is_overdue)
        self.assertTrue(self.parent.is_active)

    def test_rejects_non_extension(self):
        booking = Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date(),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
        )
        result = booking.complete_extension_externally_paid(Decimal('500.00'))
        self.assertFalse(result)


class ActivateExternallyPaidTest(ManagerFlowTestMixin, TestCase):
    """Прямые тесты Booking.activate_externally_paid."""

    def setUp(self):
        self.create_base()
        self.customer = User.objects.create_user(
            email='direct@example.com', password='p123456789',
            first_name='D', last_name='C',
        )

    def _make_booking(self, payment_method=Booking.PaymentMethod.CASH):
        return Booking.objects.create(
            user=self.customer,
            tariff=self.tariff,
            period=self.period,
            start_date=timezone.now().date(),
            quantity=1,
            unit_price_aed=Decimal('500.00'),
            price_aed=Decimal('500.00'),
            addons_aed=Decimal('0'),
            deposit_aed=Decimal('0'),
            total_aed=Decimal('500.00'),
            payment_method=payment_method,
        )

    def test_activates_with_amount_and_assigns_unit(self):
        booking = self._make_booking()
        ok = booking.activate_externally_paid(Decimal('500.00'))
        self.assertTrue(ok)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAID)
        self.assertEqual(booking.payment_amount_collected, Decimal('500.00'))
        self.assertIsNotNone(booking.paid_at)
        self.assertEqual(booking.booking_units.count(), 1)

    def test_uses_specific_unit_when_given(self):
        booking = self._make_booking()
        target = self.units[1]
        booking.activate_externally_paid(Decimal('500.00'), storage_unit=target)
        booking.refresh_from_db()
        self.assertEqual(booking.storage_unit_id, target.pk)

    def test_rejects_unavailable_unit(self):
        first = self._make_booking()
        first.activate_externally_paid(Decimal('500.00'), storage_unit=self.units[0])

        second = self._make_booking()
        with self.assertRaises(ValueError):
            second.activate_externally_paid(Decimal('500.00'), storage_unit=self.units[0])

    def test_does_not_activate_non_pending(self):
        booking = self._make_booking()
        booking.cancel()
        result = booking.activate_externally_paid(Decimal('500.00'))
        self.assertFalse(result)
