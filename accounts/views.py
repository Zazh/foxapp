from django.contrib.auth import login, logout, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings

import json

from django.shortcuts import render, redirect
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.urls import reverse

from .forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from .tokens import password_reset_token, email_verification_token
from .services import send_verification_email, send_password_reset_email

User = get_user_model()


def register_view(request):
    """Регистрация нового пользователя"""
    if request.user.is_authenticated:
        return redirect('cabinet-dashboard')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.language = request.LANGUAGE_CODE
            user.save(update_fields=['language'])

            # Отправить письмо верификации
            send_verification_email(request, user)

            # Сразу логиним пользователя (без подтверждения email)
            login(request, user)

            # Redirect на next если есть, иначе на register_done
            next_url = request.POST.get('next', '')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            return redirect('register_done')
    else:
        form = RegisterForm()

    return render(request, 'auth/register.html', {
        'form': form,
        'next': next_url,
    })


def register_done_view(request):
    """Страница после регистрации — проверьте почту"""
    return render(request, 'auth/register-done.html')


def verify_email_view(request, uidb64, token):
    """Подтверждение email"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and email_verification_token.check_token(user, token):
        user.is_verified = True
        user.save(update_fields=['is_verified'])

        login(request, user)

        # Отправить welcome уведомление
        try:
            from notifications.services import notify_welcome
            notify_welcome(user)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Welcome notification error: {e}")

        messages.success(request, _('Email verified successfully! Welcome to FoxBox.'))
        return redirect('cabinet-dashboard')
    else:
        return render(request, 'auth/verify-email-invalid.html')

def login_view(request):
    """Вход в аккаунт"""
    if request.user.is_authenticated:
        return redirect('cabinet-dashboard')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            user = form.get_user()

            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)

            login(request, user)

            if user.language:
                request.session['django_language'] = user.language

            # Проверить next из POST или GET
            next_url = request.POST.get('next') or request.GET.get('next', '')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('cabinet-dashboard')
    else:
        form = LoginForm()

    return render(request, 'auth/login.html', {
        'form': form,
        'next': next_url,
    })

def logout_view(request):
    """Выход из аккаунта"""
    logout(request)
    messages.info(request, _('You have been logged out.'))
    return redirect('home')


def forgot_password_view(request):
    """Страница запроса сброса пароля"""
    if request.user.is_authenticated:
        return redirect('cabinet-dashboard')

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email, is_active=True)
                send_password_reset_email(request, user)
            except User.DoesNotExist:
                pass  # Не раскрываем существует ли email

            # Всегда редиректим на done (безопасность)
            return redirect('forgot_password_done')
    else:
        form = ForgotPasswordForm()

    return render(request, 'auth/forgot-password.html', {'form': form})


def forgot_password_done_view(request):
    """Страница после отправки письма сброса"""
    return render(request, 'auth/forgot-password-done.html')


def reset_password_view(request, uidb64, token):
    """Установка нового пароля"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not password_reset_token.check_token(user, token):
        return render(request, 'auth/reset-password-invalid.html')

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, _('Password reset successfully! You can now sign in.'))
            return redirect('login')
    else:
        form = ResetPasswordForm()

    return render(request, 'auth/reset-password.html', {
        'form': form,
        'uidb64': uidb64,
        'token': token,
    })


@require_POST
def telegram_generate_link(request):
    """Генерация ссылки для привязки Telegram"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    from .models import TelegramLinkToken

    token = TelegramLinkToken.create_for_user(request.user)
    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'foxbox_notify_bot')

    link = f"https://t.me/{bot_username}?start={token.token}"

    return JsonResponse({
        'success': True,
        'link': link,
        'expires_in': 30  # минут
    })

@require_POST
def telegram_disconnect(request):
    """Отключить Telegram"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    user = request.user
    user.telegram_id = None
    user.telegram_username = ''
    user.save(update_fields=['telegram_id', 'telegram_username'])

    return JsonResponse({'success': True})

@csrf_exempt
@require_POST
def telegram_webhook(request):
    """Webhook для Telegram бота"""
    # Проверка секретного токена (опционально)
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    expected_secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')

    if expected_secret and secret != expected_secret:
        return JsonResponse({'error': 'Invalid secret'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    message = data.get('message', {})
    text = message.get('text', '')
    chat = message.get('chat', {})
    chat_id = chat.get('id')

    if not chat_id:
        return JsonResponse({'ok': True})

    # Обработка команды /start с токеном
    if text.startswith('/start '):
        token_value = text.replace('/start ', '').strip()

        from .models import TelegramLinkToken, User
        from django.utils import timezone

        try:
            token = TelegramLinkToken.objects.select_related('user').get(
                token=token_value,
                is_used=False,
                expires_at__gt=timezone.now()
            )

            # Привязать Telegram к пользователю
            user = token.user
            user.telegram_id = chat_id
            user.telegram_username = chat.get('username', '')
            user.save(update_fields=['telegram_id', 'telegram_username'])

            # Отметить токен использованным
            token.is_used = True
            token.save(update_fields=['is_used'])

            # Отправить подтверждение
            send_telegram_message(chat_id,
                                  f"✅ Telegram connected!\n\nHello {user.first_name}! You will now receive notifications here.")

        except TelegramLinkToken.DoesNotExist:
            send_telegram_message(chat_id,
                                  "❌ Invalid or expired link.\n\nPlease generate a new link in your FoxBox account.")

    elif text == '/start':
        send_telegram_message(chat_id,
                              "👋 Welcome to FoxBox!\n\nTo receive notifications, please connect your Telegram in your FoxBox account settings.")

    elif text == '/disconnect':
        # Отключить уведомления
        from .models import User
        try:
            user = User.objects.get(telegram_id=chat_id)
            user.telegram_id = None
            user.telegram_username = ''
            user.save(update_fields=['telegram_id', 'telegram_username'])
            send_telegram_message(chat_id, "✅ Telegram disconnected.\n\nYou will no longer receive notifications.")
        except User.DoesNotExist:
            send_telegram_message(chat_id, "You don't have a connected account.")

    return JsonResponse({'ok': True})


def send_telegram_message(chat_id, text):
    """Отправить сообщение в Telegram"""
    import requests

    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        return

    try:
        requests.post(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10
        )
    except Exception:
        pass