import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from django.conf import settings
from django.template import Template, Context
from django.utils import timezone

from .models import NotificationTemplate, NotificationLog

logger = logging.getLogger(__name__)


class EmailClient:
    """Клиент для отправки email через SMTP"""

    @classmethod
    def send_email(cls, to_email, to_name, subject, text):
        """Отправить email"""
        smtp_host = settings.EMAIL_HOST
        smtp_port = settings.EMAIL_PORT
        smtp_user = settings.EMAIL_HOST_USER
        smtp_password = settings.EMAIL_HOST_PASSWORD
        from_email = settings.DEFAULT_FROM_EMAIL
        from_name = getattr(settings, 'EMAIL_FROM_NAME', 'FoxBox')

        msg = MIMEMultipart()
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = f"{to_name} <{to_email}>"
        msg['Subject'] = subject
        msg.attach(MIMEText(text, 'plain', 'utf-8'))

        try:
            if settings.EMAIL_USE_SSL:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if settings.EMAIL_USE_TLS:
                    server.starttls()

            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_email, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            raise


class NotificationService:
    """Сервис отправки уведомлений"""

    @classmethod
    def send(cls, user, notification_type, context_data=None):
        """Отправить уведомление пользователю"""
        context_data = context_data or {}
        context_data['user'] = user

        templates = NotificationTemplate.objects.filter(
            notification_type=notification_type,
            is_active=True
        )

        for template in templates:
            if template.channel == NotificationTemplate.Channel.EMAIL and user.email:
                cls._send_email(user, template, context_data)

            if template.channel == NotificationTemplate.Channel.TELEGRAM and user.telegram_id:
                cls._send_telegram(user, template, context_data)

    @classmethod
    def _render(cls, template_string, context_data):
        """Рендер шаблона"""
        if not template_string:
            return ''
        try:
            template = Template(template_string)
            return template.render(Context(context_data))
        except Exception as e:
            logger.error(f"Template render error: {e}")
            return template_string

    @classmethod
    def _send_email(cls, user, template, context_data):
        """Отправить email"""
        subject = cls._render(template.email_subject, context_data)
        body = cls._render(template.email_body, context_data)

        log = NotificationLog.objects.create(
            user=user,
            notification_type=template.notification_type,
            channel=NotificationTemplate.Channel.EMAIL,
            recipient=user.email,
            subject=subject,
            body=body
        )

        try:
            EmailClient.send_email(
                to_email=user.email,
                to_name=user.get_full_name() or user.email,
                subject=subject,
                text=body
            )

            log.status = NotificationLog.Status.SENT
            log.sent_at = timezone.now()
            log.save(update_fields=['status', 'sent_at'])

            logger.info(f"Email sent: {template.notification_type} → {user.email}")

        except Exception as e:
            log.status = NotificationLog.Status.FAILED
            log.error_message = str(e)
            log.save(update_fields=['status', 'error_message'])

            logger.error(f"Email failed: {user.email}: {e}")

    @classmethod
    def _send_telegram(cls, user, template, context_data):
        """Отправить сообщение в Telegram"""
        import requests

        if not user.telegram_id:
            return

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return

        message = cls._render(template.telegram_message, context_data)
        if not message:
            return

        log = NotificationLog.objects.create(
            user=user,
            notification_type=template.notification_type,
            channel=NotificationTemplate.Channel.TELEGRAM,
            recipient=str(user.telegram_id),
            body=message
        )

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    'chat_id': user.telegram_id,
                    'text': message,
                    'parse_mode': 'HTML'
                },
                timeout=10
            )
            response.raise_for_status()

            log.status = NotificationLog.Status.SENT
            log.sent_at = timezone.now()
            log.save(update_fields=['status', 'sent_at'])

            logger.info(f"Telegram sent: {template.notification_type} → {user.telegram_id}")

        except Exception as e:
            log.status = NotificationLog.Status.FAILED
            log.error_message = str(e)
            log.save(update_fields=['status', 'error_message'])

            logger.error(f"Telegram failed: {user.telegram_id}: {e}")


# === Shortcut functions ===

def notify_booking_paid(booking):
    """Уведомление об оплате"""
    NotificationService.send(
        user=booking.user,
        notification_type=NotificationTemplate.NotificationType.BOOKING_PAID,
        context_data={
            'booking': booking,
            'tariff': booking.tariff,
            'unit': booking.storage_unit,
            'location': booking.tariff.location,
            'start_date': booking.start_date,
            'end_date': booking.end_date,
            'total': booking.total_aed,
        }
    )


def notify_booking_expiring(booking, days_left):
    """Уведомление о скором истечении"""
    NotificationService.send(
        user=booking.user,
        notification_type=NotificationTemplate.NotificationType.BOOKING_EXPIRING,
        context_data={
            'booking': booking,
            'unit': booking.storage_unit,
            'days_left': days_left,
            'end_date': booking.end_date,
        }
    )


def notify_visit(visit):
    """Уведомление о посещении"""
    notification_type = (
        NotificationTemplate.NotificationType.GUEST_VISIT
        if visit.visitor_type == 'guest'
        else NotificationTemplate.NotificationType.VISIT_LOGGED
    )

    NotificationService.send(
        user=visit.booking.user,
        notification_type=notification_type,
        context_data={
            'visit': visit,
            'unit': visit.booking.storage_unit,
            'visitor_name': visit.visitor_name,
            'visited_at': visit.visited_at,
        }
    )


def notify_welcome(user):
    """Приветственное уведомление"""
    NotificationService.send(
        user=user,
        notification_type=NotificationTemplate.NotificationType.WELCOME
    )