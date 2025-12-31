from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from notifications.services import EmailClient, NotificationService
from notifications.models import NotificationTemplate

User = get_user_model()


class Command(BaseCommand):
    help = 'Test notifications'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Test email address')
        parser.add_argument('--telegram', type=int, help='Test Telegram ID')
        parser.add_argument('--user-id', type=int, help='User ID to test with')

    def handle(self, *args, **options):
        # Тест отправки email
        if options['email']:
            self.stdout.write(f'\n=== Testing Email to {options["email"]} ===')
            try:
                EmailClient.send_email(
                    to_email=options['email'],
                    to_name='Test User',
                    subject='FoxBox Test Email',
                    text='This is a test email from FoxBox.\n\nIf you received this, email is working!'
                )
                self.stdout.write(self.style.SUCCESS('✓ Email sent successfully'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Email ERROR: {e}'))

        # Тест Telegram
        if options['telegram']:
            self.stdout.write(f'\n=== Testing Telegram to {options["telegram"]} ===')
            try:
                import requests
                from django.conf import settings

                bot_token = settings.TELEGRAM_BOT_TOKEN
                if not bot_token:
                    self.stdout.write(self.style.ERROR('✗ TELEGRAM_BOT_TOKEN not set'))
                else:
                    response = requests.post(
                        f'https://api.telegram.org/bot{bot_token}/sendMessage',
                        json={
                            'chat_id': options['telegram'],
                            'text': '✅ FoxBox Test\n\nIf you received this, Telegram is working!'
                        },
                        timeout=10
                    )
                    if response.status_code == 200:
                        self.stdout.write(self.style.SUCCESS('✓ Telegram sent successfully'))
                    else:
                        self.stdout.write(self.style.ERROR(f'✗ Telegram ERROR: {response.text}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Telegram ERROR: {e}'))

        # Тест полного flow с пользователем
        if options['user_id']:
            self.stdout.write(f'\n=== Testing Full Flow for User #{options["user_id"]} ===')
            try:
                user = User.objects.get(pk=options['user_id'])
                self.stdout.write(f'User: {user.email}')
                self.stdout.write(f'Telegram ID: {user.telegram_id or "Not set"}')

                templates = NotificationTemplate.objects.filter(
                    notification_type=NotificationTemplate.NotificationType.WELCOME,
                    is_active=True
                )
                self.stdout.write(f'Welcome templates: {templates.count()}')

                if templates.exists():
                    from notifications.services import notify_welcome
                    notify_welcome(user)
                    self.stdout.write(self.style.SUCCESS('✓ Welcome notification sent'))
                else:
                    self.stdout.write(self.style.WARNING('⚠ No welcome templates found'))

            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'✗ User #{options["user_id"]} not found'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ ERROR: {e}'))

        if not any([options['email'], options['telegram'], options['user_id']]):
            self.stdout.write('Usage:')
            self.stdout.write('  --email=your@email.com  Test email sending')
            self.stdout.write('  --telegram=123456789    Test Telegram sending')
            self.stdout.write('  --user-id=1             Test full flow for user')

        self.stdout.write('\n=== Done ===\n')