from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.conf import settings

from .tokens import email_verification_token, password_reset_token


def send_verification_email(request, user):
    """Отправка письма для подтверждения email"""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)

    # Используем reverse для правильного URL
    verify_path = reverse('verify_email', kwargs={'uidb64': uid, 'token': token})
    verify_url = request.build_absolute_uri(verify_path)

    subject = 'Verify your email - FoxBox'
    message = f'''
Hello {user.get_short_name()},

Please verify your email by clicking the link below:

{verify_url}

This link will expire in 24 hours.

If you didn't create an account, please ignore this email.

Best regards,
FoxBox Team
    '''

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(request, user):
    """Отправка письма для сброса пароля"""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_reset_token.make_token(user)

    # Используем reverse для правильного URL
    reset_path = reverse('reset_password', kwargs={'uidb64': uid, 'token': token})
    reset_url = request.build_absolute_uri(reset_path)

    subject = 'Reset your password - FoxBox'
    message = f'''
Hello {user.get_short_name()},

You requested a password reset. Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.

Best regards,
FoxBox Team
    '''

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )