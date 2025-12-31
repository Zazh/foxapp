from django.core.management.base import BaseCommand
from notifications.models import NotificationTemplate


class Command(BaseCommand):
    help = 'Create default notification templates'

    def handle(self, *args, **options):
        templates = [
            # Booking Paid
            {
                'notification_type': 'booking_paid',
                'channel': 'email',
                'email_subject': 'FoxBox: Booking #{{ booking.id }} confirmed',
                'email_body': '''Hello {{ user.first_name }}!

Your booking has been confirmed.

Unit: {{ unit.full_code }}
Tariff: {{ tariff.name }}
Location: {{ location.name }}
Period: {{ start_date }} - {{ end_date }}
Total: AED {{ total }}

Thank you for choosing FoxBox!

--
FoxBox Team
https://foxbox.ae''',
            },
            {
                'notification_type': 'booking_paid',
                'channel': 'telegram',
                'telegram_message': '''✅ Booking Confirmed!

Unit: {{ unit.full_code }}
Tariff: {{ tariff.name }}
Period: {{ start_date }} - {{ end_date }}
Total: AED {{ total }}

Thank you for choosing FoxBox!''',
            },
            # Booking Expiring
            {
                'notification_type': 'booking_expiring',
                'channel': 'email',
                'email_subject': 'FoxBox: Your rental expires in {{ days_left }} days',
                'email_body': '''Hello {{ user.first_name }}!

Your rental is expiring soon.

Unit: {{ unit.full_code }}
Expires: {{ end_date }}
Days left: {{ days_left }}

To extend your rental, visit your dashboard:
https://foxbox.ae/cabinet/

--
FoxBox Team''',
            },
            {
                'notification_type': 'booking_expiring',
                'channel': 'telegram',
                'telegram_message': '''⚠️ Rental Expiring Soon!

Unit: {{ unit.full_code }}
Expires: {{ end_date }}
Days left: {{ days_left }}

Extend now: https://foxbox.ae/cabinet/''',
            },
            # Booking Expired
            {
                'notification_type': 'booking_expired',
                'channel': 'email',
                'email_subject': 'FoxBox: Your rental has expired',
                'email_body': '''Hello {{ user.first_name }}!

Your rental has expired.

Unit: {{ unit.full_code }}
Expired: {{ end_date }}

Please collect your belongings or renew your rental:
https://foxbox.ae/cabinet/

--
FoxBox Team''',
            },
            {
                'notification_type': 'booking_expired',
                'channel': 'telegram',
                'telegram_message': '''🔴 Rental Expired!

Unit: {{ unit.full_code }}
Expired: {{ end_date }}

Please collect your belongings or renew:
https://foxbox.ae/cabinet/''',
            },
            # Guest Visit
            {
                'notification_type': 'guest_visit',
                'channel': 'email',
                'email_subject': 'FoxBox: Guest accessed your unit',
                'email_body': '''Hello {{ user.first_name }}!

A guest has accessed your unit.

Unit: {{ unit.full_code }}
Guest: {{ visitor_name }}
Time: {{ visited_at }}

If this was not authorized, please contact us immediately.

--
FoxBox Team''',
            },
            {
                'notification_type': 'guest_visit',
                'channel': 'telegram',
                'telegram_message': '''👤 Guest Access

Unit: {{ unit.full_code }}
Guest: {{ visitor_name }}
Time: {{ visited_at }}

If not authorized, contact us!''',
            },
            # Visit Logged
            {
                'notification_type': 'visit_logged',
                'channel': 'telegram',
                'telegram_message': '''🚪 Unit Access

Unit: {{ unit.full_code }}
Time: {{ visited_at }}

You have accessed your unit.''',
            },
            # Welcome
            {
                'notification_type': 'welcome',
                'channel': 'email',
                'email_subject': 'Welcome to FoxBox!',
                'email_body': '''Hello {{ user.first_name }}!

Welcome to FoxBox - your secure storage solution in UAE.

Your account has been created successfully.

To get started, browse our services:
https://foxbox.ae/

If you have any questions, feel free to contact us.

--
FoxBox Team
https://foxbox.ae''',
            },
        ]

        created = 0
        updated = 0

        for data in templates:
            obj, is_created = NotificationTemplate.objects.update_or_create(
                notification_type=data['notification_type'],
                channel=data['channel'],
                defaults={
                    'email_subject': data.get('email_subject', ''),
                    'email_body': data.get('email_body', ''),
                    'telegram_message': data.get('telegram_message', ''),
                    'is_active': True,
                }
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Created: {created}, Updated: {updated}'))