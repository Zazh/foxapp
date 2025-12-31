import json
import secrets
import requests
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login
from django.http import HttpResponseBadRequest

from .models import User

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'


def google_login(request):
    """Инициировать Google OAuth"""

    # Сохраняем next URL в state
    next_url = request.GET.get('next', '')
    state_data = {
        'next': next_url,
        'csrf': secrets.token_urlsafe(16)
    }
    # Сохраняем state в сессии для проверки
    request.session['google_oauth_state'] = state_data

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'state': json.dumps(state_data),
        'prompt': 'select_account',  # Всегда показывать выбор аккаунта
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return redirect(auth_url)


def google_callback(request):
    """Обработка callback от Google"""

    error = request.GET.get('error')
    if error:
        # Пользователь отменил или ошибка
        return redirect('login')

    code = request.GET.get('code')
    state = request.GET.get('state')

    if not code:
        return HttpResponseBadRequest('Missing code parameter')

    # Проверяем state
    try:
        state_data = json.loads(state) if state else {}
    except json.JSONDecodeError:
        state_data = {}

    saved_state = request.session.get('google_oauth_state', {})
    if state_data.get('csrf') != saved_state.get('csrf'):
        return HttpResponseBadRequest('Invalid state parameter')

    next_url = state_data.get('next', '')

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
    except requests.RequestException:
        return redirect('login')

    access_token = tokens.get('access_token')
    if not access_token:
        return redirect('login')

    # Получаем информацию о пользователе
    try:
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except requests.RequestException:
        return redirect('login')

    google_id = userinfo.get('id')
    email = userinfo.get('email')
    first_name = userinfo.get('given_name', '')
    last_name = userinfo.get('family_name', '')

    if not email:
        return redirect('login')

    # Ищем или создаём пользователя
    user = None

    # 1. Сначала ищем по provider_id (уже регистрировался через Google)
    user = User.objects.filter(auth_provider='google', provider_id=google_id).first()

    # 2. Если не нашли — ищем по email
    if not user:
        user = User.objects.filter(email=email).first()

        if user:
            # Пользователь существует с этим email
            if user.auth_provider == 'email':
                # Связываем существующий email-аккаунт с Google
                user.auth_provider = 'google'
                user.provider_id = google_id
                user.is_verified = True  # Google уже подтвердил email
                user.save(update_fields=['auth_provider', 'provider_id', 'is_verified'])

    # 3. Создаём нового пользователя
    if not user:
        user = User.objects.create(
            email=email,
            first_name=first_name or 'User',
            last_name=last_name or '',
            phone='',  # Пустой, заполнит позже
            id_card='',  # Пустой, заполнит позже
            auth_provider='google',
            provider_id=google_id,
            is_verified=True,
            language=request.session.get('django_language', 'en'),
        )

        # Отправить welcome уведомление
        try:
            from notifications.services import notify_welcome
            notify_welcome(user)
        except Exception:
            pass

    # Логиним пользователя
    login(request, user)

    # Устанавливаем язык
    if user.language:
        request.session['django_language'] = user.language

    # Очищаем state из сессии
    request.session.pop('google_oauth_state', None)

    # Редирект
    if next_url and next_url.startswith('/'):
        return redirect(next_url)

    # Если у пользователя не заполнены обязательные поля — на настройки
    if not user.phone or not user.id_card:
        return redirect('cabinet-settings')

    return redirect('cabinet-dashboard')