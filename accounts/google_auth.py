import logging
import secrets
from urllib.parse import urlencode

import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core import signing
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from .models import User

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

# Подписываем state-токен этой солью, чтобы любой посторонний токен,
# подписанный SECRET_KEY для других целей, не прошёл валидацию.
STATE_SALT = 'accounts.google_auth.state.v1'
STATE_MAX_AGE = 600  # 10 минут на завершение OAuth flow


def _build_state(next_url):
    # Ранее state хранился в session['google_oauth_state'] — один ключ
    # на всю сессию, перезаписываемый при каждом клике «Sign in with
    # Google». Это ломало параллельные попытки в разных вкладках:
    # вторая попытка затирала csrf-токен первой, и завершившая первой
    # вкладка падала с «Invalid state parameter». Подписанный токен
    # переносит next и одноразовый nonce внутри самого state — сессия
    # вообще не нужна для CSRF-проверки, гонок больше нет.
    payload = {
        'next': next_url or '',
        'nonce': secrets.token_urlsafe(16),
    }
    return signing.dumps(payload, salt=STATE_SALT, compress=True)


def _verify_state(state):
    if not state:
        return None
    try:
        return signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature:
        return None


def _redirect_with_error(request, msg):
    messages.error(request, msg)
    return redirect('login')


def google_login(request):
    """Инициировать Google OAuth"""
    next_url = request.GET.get('next', '')

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'state': _build_state(next_url),
        'prompt': 'select_account',
    }

    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


def google_callback(request):
    """Обработка callback от Google"""
    error = request.GET.get('error')
    if error:
        logger.info('Google OAuth: provider returned error=%s', error)
        return _redirect_with_error(request, _('Google sign-in was cancelled.'))

    code = request.GET.get('code', '')
    state = request.GET.get('state', '')

    if not code:
        return _redirect_with_error(
            request,
            _('Google sign-in failed. Please try again.'),
        )

    payload = _verify_state(state)
    if payload is None:
        logger.info('Google OAuth: invalid or expired state')
        return _redirect_with_error(
            request,
            _('Sign-in link expired. Please try signing in again.'),
        )

    next_url = payload.get('next', '')

    # Обмен code на access token
    token_data = {
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }

    try:
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=10)
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.RequestException as e:
        logger.warning('Google OAuth: token exchange failed: %s', e)
        return _redirect_with_error(
            request,
            _('Could not connect to Google. Please try again.'),
        )

    access_token = tokens.get('access_token')
    if not access_token:
        return _redirect_with_error(
            request,
            _('Google did not return an access token. Please try again.'),
        )

    # Получаем информацию о пользователе
    try:
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except requests.RequestException as e:
        logger.warning('Google OAuth: userinfo fetch failed: %s', e)
        return _redirect_with_error(
            request,
            _('Could not fetch your Google profile. Please try again.'),
        )

    google_id = userinfo.get('id')
    email = (userinfo.get('email') or '').lower()
    first_name = userinfo.get('given_name', '')
    last_name = userinfo.get('family_name', '')

    if not email or not google_id:
        return _redirect_with_error(
            request,
            _('Google did not provide a valid email address.'),
        )

    # 1. Сначала ищем по provider_id (уже регистрировался через Google)
    user = User.objects.filter(auth_provider='google', provider_id=google_id).first()

    # 2. Если не нашли — ищем по email (case-insensitive,
    # чтобы не плодить дубли при разной капитализации)
    if not user:
        user = User.objects.filter(email__iexact=email).first()

        if user and user.auth_provider == 'email':
            # Связываем существующий email-аккаунт с Google
            user.auth_provider = 'google'
            user.provider_id = google_id
            user.is_verified = True
            user.save(update_fields=['auth_provider', 'provider_id', 'is_verified'])

    # 3. Создаём нового пользователя
    if not user:
        user = User.objects.create(
            email=email,
            first_name=first_name or 'User',
            last_name=last_name or '',
            phone='',
            id_card=None,
            auth_provider='google',
            provider_id=google_id,
            is_verified=True,
            language=request.session.get('django_language', 'en'),
        )
        # Без этого password='' и любое .check_password() вернёт True
        # для пустой строки, что небезопасно.
        user.set_unusable_password()
        user.save(update_fields=['password'])

        try:
            from notifications.services import notify_welcome
            notify_welcome(user)
        except Exception as e:
            logger.warning('notify_welcome failed for %s: %s', user.email, e)

    login(request, user)

    if user.language:
        request.session['django_language'] = user.language

    if next_url and next_url.startswith('/'):
        return redirect(next_url)

    return redirect('cabinet-dashboard')
