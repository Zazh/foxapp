from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import FeedbackRequest


class FeedbackSubmitView(View):
    """Отправка заявки на обратную связь"""

    def post(self, request):
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()

        # Валидация
        if not name or not phone:
            return JsonResponse({
                'success': False,
                'error': 'Name and phone are required'
            }, status=400)

        # Получить метаданные
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Создать заявку
        feedback = FeedbackRequest.objects.create(
            name=name,
            phone=phone,
            email=email,
            message=message,
            user=request.user if request.user.is_authenticated else None,
            page_url=request.META.get('HTTP_REFERER', ''),
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )

        # Уведомление менеджерам (опционально)
        try:
            self.notify_managers(feedback)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Feedback notification error: {e}")

        return JsonResponse({
            'success': True,
            'message': 'Thank you! We will contact you shortly.'
        })

    def notify_managers(self, feedback):
        """Отправить уведомление менеджерам в Telegram"""
        from django.conf import settings
        import requests

        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        manager_chat_id = getattr(settings, 'TELEGRAM_MANAGER_CHAT_ID', '')

        if not bot_token or not manager_chat_id:
            return

        message = f"""📩 New Feedback Request!

Name: {feedback.name}
Phone: {feedback.phone}
Email: {feedback.email or '—'}
Message: {feedback.message or '—'}

Page: {feedback.page_url or '—'}
Time: {feedback.created_at.strftime('%Y-%m-%d %H:%M')}"""

        try:
            requests.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json={'chat_id': manager_chat_id, 'text': message},
                timeout=10
            )
        except Exception:
            pass