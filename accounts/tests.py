from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core import signing
from django.test import TestCase
from django.urls import reverse

from accounts.google_auth import (
    STATE_SALT,
    _build_state,
    _verify_state,
)

User = get_user_model()


class GoogleStateTokenTests(TestCase):
    """Подписанный state — это и есть фикс «Invalid state parameter»."""

    def test_build_and_verify_roundtrip(self):
        state = _build_state('/booking/foo/')
        payload = _verify_state(state)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['next'], '/booking/foo/')
        self.assertIn('nonce', payload)

    def test_empty_next_roundtrip(self):
        payload = _verify_state(_build_state(''))
        self.assertEqual(payload['next'], '')

    def test_verify_rejects_tampered_state(self):
        state = _build_state('/foo/')
        bad = state[:-2] + ('AB' if not state.endswith('AB') else 'CD')
        self.assertIsNone(_verify_state(bad))

    def test_verify_rejects_empty_or_none(self):
        self.assertIsNone(_verify_state(''))
        self.assertIsNone(_verify_state(None))

    def test_verify_rejects_garbage(self):
        self.assertIsNone(_verify_state('not-even-a-token'))

    def test_verify_rejects_wrong_salt(self):
        # Токен с правильным SECRET_KEY, но другой солью — не должен пройти.
        bad = signing.dumps({'next': '/'}, salt='other.salt')
        self.assertIsNone(_verify_state(bad))

    def test_two_parallel_states_are_both_valid(self):
        """Прямое доказательство, что нет single-key race из старого кода:
        две вкладки могут одновременно начать OAuth и обе завершить успешно."""
        state_a = _build_state('/page-a/')
        state_b = _build_state('/page-b/')
        self.assertEqual(_verify_state(state_a)['next'], '/page-a/')
        self.assertEqual(_verify_state(state_b)['next'], '/page-b/')
        # nonces разные
        self.assertNotEqual(
            _verify_state(state_a)['nonce'],
            _verify_state(state_b)['nonce'],
        )

    def test_state_expires(self):
        """Старые state-токены не должны работать вечно."""
        state = _build_state('/x/')
        # Мокаем max_age=0 → всё уже просрочено
        with patch(
            'accounts.google_auth.STATE_MAX_AGE', new=-1
        ):
            self.assertIsNone(_verify_state(state))


class GoogleLoginViewTests(TestCase):
    def test_google_login_redirects_to_provider_with_state(self):
        response = self.client.get(reverse('google_login'), {'next': '/booking/x/'})
        self.assertEqual(response.status_code, 302)
        location = response['Location']
        self.assertTrue(location.startswith('https://accounts.google.com/'))
        # state есть в query
        self.assertIn('state=', location)
        # next зашит в state, а не в URL отдельно
        self.assertNotIn('next=%2Fbooking%2Fx%2F', location)


class GoogleCallbackViewTests(TestCase):
    def setUp(self):
        self.url = reverse('google_callback')
        self.login_url = reverse('login')

    def test_callback_without_state_redirects_to_login_with_error(self):
        response = self.client.get(self.url, {'code': 'fake-code'})
        self.assertRedirects(response, self.login_url)
        msgs = list(get_messages(response.wsgi_request))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].level_tag, 'error')

    def test_callback_with_invalid_state_redirects_to_login(self):
        response = self.client.get(
            self.url,
            {'code': 'fake-code', 'state': 'tampered-state-value'},
        )
        self.assertRedirects(response, self.login_url)
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any(m.level_tag == 'error' for m in msgs))

    def test_callback_with_provider_error_redirects_to_login(self):
        response = self.client.get(self.url, {'error': 'access_denied'})
        self.assertRedirects(response, self.login_url)

    def test_callback_without_code_redirects_to_login(self):
        # Даже с валидным state — без code обмен невозможен
        state = _build_state('')
        response = self.client.get(self.url, {'state': state})
        self.assertRedirects(response, self.login_url)

    @patch('accounts.google_auth.requests.get')
    @patch('accounts.google_auth.requests.post')
    def test_callback_creates_new_user(self, mock_post, mock_get):
        mock_post.return_value = MagicMock(
            json=lambda: {'access_token': 'fake-access-token'},
            raise_for_status=lambda: None,
        )
        mock_get.return_value = MagicMock(
            json=lambda: {
                'id': 'google-uid-123',
                'email': 'newuser@example.com',
                'given_name': 'New',
                'family_name': 'User',
            },
            raise_for_status=lambda: None,
        )

        state = _build_state('/cabinet/')
        response = self.client.get(
            self.url,
            {'code': 'fake-code', 'state': state},
        )

        # Должен редирект на next='/cabinet/'
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/cabinet/')

        user = User.objects.get(email='newuser@example.com')
        self.assertEqual(user.auth_provider, 'google')
        self.assertEqual(user.provider_id, 'google-uid-123')
        self.assertTrue(user.is_verified)
        self.assertFalse(user.has_usable_password())

    @patch('accounts.google_auth.requests.get')
    @patch('accounts.google_auth.requests.post')
    def test_callback_links_existing_email_user_to_google(
        self, mock_post, mock_get
    ):
        existing = User.objects.create_user(
            email='existing@example.com',
            password='SomePass123!',
            first_name='Existing',
            last_name='User',
            phone='+971500000000',
            id_card='OLD-1',
        )
        self.assertEqual(existing.auth_provider, 'email')

        mock_post.return_value = MagicMock(
            json=lambda: {'access_token': 'fake-access-token'},
            raise_for_status=lambda: None,
        )
        mock_get.return_value = MagicMock(
            json=lambda: {
                'id': 'google-uid-456',
                'email': 'existing@example.com',
                'given_name': 'Existing',
                'family_name': 'User',
            },
            raise_for_status=lambda: None,
        )

        state = _build_state('')
        response = self.client.get(
            self.url,
            {'code': 'fake-code', 'state': state},
        )
        self.assertEqual(response.status_code, 302)

        existing.refresh_from_db()
        self.assertEqual(existing.auth_provider, 'google')
        self.assertEqual(existing.provider_id, 'google-uid-456')
        self.assertTrue(existing.is_verified)

    @patch('accounts.google_auth.requests.get')
    @patch('accounts.google_auth.requests.post')
    def test_callback_links_by_email_case_insensitive(
        self, mock_post, mock_get
    ):
        existing = User.objects.create_user(
            email='Mixed.Case@Example.com'.lower(),
            password='SomePass123!',
            first_name='X',
            last_name='Y',
            phone='+971500000010',
            id_card='OLD-2',
        )

        mock_post.return_value = MagicMock(
            json=lambda: {'access_token': 'fake-access-token'},
            raise_for_status=lambda: None,
        )
        mock_get.return_value = MagicMock(
            json=lambda: {
                'id': 'google-uid-789',
                'email': 'MIXED.CASE@example.com',
                'given_name': 'X',
                'family_name': 'Y',
            },
            raise_for_status=lambda: None,
        )

        state = _build_state('')
        self.client.get(self.url, {'code': 'fake-code', 'state': state})

        # Не должно быть второго юзера с тем же email в другом регистре
        self.assertEqual(User.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.auth_provider, 'google')

    @patch('accounts.google_auth.requests.post')
    def test_callback_handles_token_exchange_failure(self, mock_post):
        import requests as rq
        mock_post.side_effect = rq.RequestException('boom')

        state = _build_state('')
        response = self.client.get(
            self.url, {'code': 'fake-code', 'state': state}
        )
        self.assertRedirects(response, self.login_url)
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any(m.level_tag == 'error' for m in msgs))

    @patch('accounts.google_auth.requests.get')
    @patch('accounts.google_auth.requests.post')
    def test_callback_rejects_response_without_email(
        self, mock_post, mock_get
    ):
        mock_post.return_value = MagicMock(
            json=lambda: {'access_token': 'fake-access-token'},
            raise_for_status=lambda: None,
        )
        mock_get.return_value = MagicMock(
            json=lambda: {'id': 'google-uid-x'},  # no email
            raise_for_status=lambda: None,
        )

        state = _build_state('')
        response = self.client.get(
            self.url, {'code': 'fake-code', 'state': state}
        )
        self.assertRedirects(response, self.login_url)
        # юзер не создан
        self.assertEqual(User.objects.count(), 0)

    @patch('accounts.google_auth.requests.get')
    @patch('accounts.google_auth.requests.post')
    def test_callback_does_not_redirect_to_external_next(
        self, mock_post, mock_get
    ):
        """Open-redirect защита: next не должен уводить наружу."""
        mock_post.return_value = MagicMock(
            json=lambda: {'access_token': 't'},
            raise_for_status=lambda: None,
        )
        mock_get.return_value = MagicMock(
            json=lambda: {
                'id': 'g-1',
                'email': 'attacker-target@example.com',
                'given_name': 'A',
                'family_name': 'B',
            },
            raise_for_status=lambda: None,
        )

        state = _build_state('https://evil.example.com/')
        response = self.client.get(
            self.url, {'code': 'fake-code', 'state': state}
        )
        self.assertEqual(response.status_code, 302)
        # Должен попасть на cabinet-dashboard, а не на evil.example.com
        self.assertNotIn('evil.example.com', response['Location'])


class RegisterViewTests(TestCase):
    def setUp(self):
        self.url = reverse('register')
        self.valid_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'id_card': 'TEST-001',
            'phone': '+971500000001',
            'email': 'test@example.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
        }

    @patch('accounts.views.send_verification_email')
    def test_successful_registration_logs_user_in_and_redirects_to_cabinet(
        self, mock_send
    ):
        response = self.client.post(self.url, self.valid_data)
        # Раньше редирект шёл на /register/done/ с пугающим текстом
        # «Click the link to activate your account» — юзеры думали,
        # что регистрация не сработала. Теперь сразу в кабинет.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('cabinet-dashboard'))

        user = User.objects.get(email='test@example.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        mock_send.assert_called_once()

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any(m.level_tag == 'success' for m in msgs),
            f'Expected success message, got: {[(m.level_tag, str(m.message)) for m in msgs]}',
        )

    def test_register_done_url_redirects_anonymous_to_login(self):
        response = self.client.get(reverse('register_done'))
        self.assertRedirects(response, reverse('login'))

    def test_register_done_url_redirects_authenticated_to_cabinet(self):
        User.objects.create_user(
            email='already@example.com',
            password='SomePass123!',
            first_name='X', last_name='Y',
            phone='+971500000099', id_card='RD-001',
        )
        self.client.login(email='already@example.com', password='SomePass123!')
        response = self.client.get(reverse('register_done'))
        self.assertRedirects(
            response, reverse('cabinet-dashboard'),
            fetch_redirect_response=False,
        )

    @patch('accounts.views.send_verification_email')
    def test_registration_succeeds_when_email_send_fails(self, mock_send):
        """Главный фикс: SMTP-сбой не ломает регистрацию.

        Раньше Mail.ru down → 500 → юзер создан, но не залогинен,
        и при повторной попытке получал «email уже существует»."""
        mock_send.side_effect = Exception('SMTP server down')

        response = self.client.post(self.url, self.valid_data)

        # Юзер всё равно создан...
        user = User.objects.get(email='test@example.com')
        # ...и залогинен
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        # Редирект (не 500)
        self.assertEqual(response.status_code, 302)

        # Редирект в кабинет, а не на 500
        self.assertEqual(response['Location'], reverse('cabinet-dashboard'))

        # И есть warning-сообщение
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any(m.level_tag == 'warning' for m in msgs),
            f'Expected a warning message, got: {[(m.level_tag, str(m.message)) for m in msgs]}',
        )

    @patch('accounts.views.send_verification_email')
    def test_registration_redirects_to_safe_next(self, mock_send):
        data = {**self.valid_data, 'next': '/booking/123/'}
        response = self.client.post(self.url, data)
        self.assertRedirects(
            response, '/booking/123/', fetch_redirect_response=False
        )

    @patch('accounts.views.send_verification_email')
    def test_registration_ignores_external_next(self, mock_send):
        data = {**self.valid_data, 'next': 'https://evil.example.com/'}
        response = self.client.post(self.url, data)
        self.assertNotEqual(response['Location'], 'https://evil.example.com/')

    def test_duplicate_email_blocked(self):
        User.objects.create_user(
            email='test@example.com',
            password='SomePass123!',
            first_name='X',
            last_name='Y',
            phone='+971500000099',
            id_card='OTHER-001',
        )
        response = self.client.post(self.url, self.valid_data)
        # Форма должна вернуться с ошибкой (200), а не упасть
        self.assertEqual(response.status_code, 200)
        # В БД остался только один юзер
        self.assertEqual(User.objects.filter(email='test@example.com').count(), 1)


class ForgotPasswordViewTests(TestCase):
    def setUp(self):
        self.url = reverse('forgot_password')
        self.user = User.objects.create_user(
            email='reset@example.com',
            password='Pass123!',
            first_name='X', last_name='Y',
            phone='+971500000123', id_card='RST-1',
        )

    @patch('accounts.views.send_password_reset_email')
    def test_html_form_success(self, mock_send):
        response = self.client.post(self.url, {'email': 'reset@example.com'})
        self.assertRedirects(response, reverse('forgot_password_done'))
        mock_send.assert_called_once()

    @patch('accounts.views.send_password_reset_email')
    def test_html_form_does_not_500_when_smtp_fails(self, mock_send):
        # Главный фикс: Mail.ru down → было бы 500, теперь redirect.
        mock_send.side_effect = Exception('SMTP down')
        response = self.client.post(self.url, {'email': 'reset@example.com'})
        self.assertRedirects(response, reverse('forgot_password_done'))

    @patch('accounts.views.send_password_reset_email')
    def test_html_form_silent_for_unknown_email(self, mock_send):
        # По безопасности не палим существование email
        response = self.client.post(self.url, {'email': 'nobody@example.com'})
        self.assertRedirects(response, reverse('forgot_password_done'))
        mock_send.assert_not_called()

    @patch('accounts.views.send_password_reset_email')
    def test_ajax_json_success(self, mock_send):
        # AJAX из модалки modal-forgot-password (body=JSON)
        response = self.client.post(
            self.url,
            data='{"email": "reset@example.com"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})
        mock_send.assert_called_once()

    @patch('accounts.views.send_password_reset_email')
    def test_ajax_json_success_when_smtp_fails(self, mock_send):
        mock_send.side_effect = Exception('SMTP down')
        response = self.client.post(
            self.url,
            data='{"email": "reset@example.com"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})

    def test_ajax_json_invalid_email_returns_400(self):
        response = self.client.post(
            self.url,
            data='{"email": "not-an-email"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertIn('error', body)

    def test_ajax_garbage_body_returns_400(self):
        response = self.client.post(
            self.url,
            data='this is not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class RegisterFormBlankIdCardTests(TestCase):
    def test_blank_id_card_rejected(self):
        from accounts.forms import RegisterForm
        form = RegisterForm({
            'first_name': 'A', 'last_name': 'B',
            'id_card': '   ',  # whitespace only
            'phone': '+971500000999',
            'email': 'blank@example.com',
            'password': 'StrongPass123!',
            'password_confirm': 'StrongPass123!',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('id_card', form.errors)


class BookingCreateGetRedirectTests(TestCase):
    """GET на /booking/.../book/ должен редиректить на тариф,
    а не отдавать 405."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='b@example.com', password='Pass123!',
            first_name='X', last_name='Y',
            phone='+971500000456', id_card='B-1',
        )
        from services.models import Service, Tariff
        from locations.models import Location
        loc = Location.objects.create(
            name='Loc', street='s', building='b',
            latitude=25.0, longitude=55.0,
        )
        self.service = Service.objects.create(
            name='Auto', service_type='auto', is_active=True,
        )
        self.tariff = Tariff.objects.create(
            service=self.service, location=loc, name='Std',
            slug='std', deposit_aed=0, is_active=True,
        )

    def test_anonymous_get_redirects_to_login(self):
        response = self.client.get(
            reverse('booking_create', args=['auto', 'std'])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_authenticated_get_redirects_to_tariff_page(self):
        self.client.login(email='b@example.com', password='Pass123!')
        response = self.client.get(
            reverse('booking_create', args=['auto', 'std'])
        )
        self.assertRedirects(
            response,
            reverse('tariff_detail', args=['auto', 'std']),
            fetch_redirect_response=False,
        )


class LoginViewTests(TestCase):
    def setUp(self):
        self.url = reverse('login')
        self.user = User.objects.create_user(
            email='login@example.com',
            password='SomePass123!',
            first_name='X',
            last_name='Y',
            phone='+971500000001',
            id_card='LOGIN-001',
        )

    def test_login_page_has_google_button(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('google_login'))
        self.assertContains(response, 'Continue with Google')

    def test_login_with_correct_credentials(self):
        response = self.client.post(
            self.url,
            {'email': 'login@example.com', 'password': 'SomePass123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_case_insensitive_email(self):
        response = self.client.post(
            self.url,
            {'email': 'LOGIN@EXAMPLE.com', 'password': 'SomePass123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_wrong_password_returns_form(self):
        response = self.client.post(
            self.url,
            {'email': 'login@example.com', 'password': 'WrongPass!'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
