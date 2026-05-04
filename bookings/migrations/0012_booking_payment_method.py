from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0011_booking_number'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='payment_method',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('lk_invoice', 'Online (Stripe Checkout in cabinet)'),
                    ('cash', 'Cash / terminal at desk'),
                    ('stripe_payment_link', 'Stripe Payment Link (manager-sent)'),
                ],
                default='lk_invoice',
                verbose_name='Payment method',
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='payment_amount_collected',
            field=models.DecimalField(
                max_digits=10, decimal_places=2,
                null=True, blank=True,
                verbose_name='Amount collected',
                help_text='Actual amount the manager collected (cash/payment_link). For reporting.',
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='created_by_manager',
            field=models.ForeignKey(
                on_delete=models.deletion.SET_NULL,
                null=True, blank=True,
                to=settings.AUTH_USER_MODEL,
                related_name='bookings_created_as_manager',
                verbose_name='Created by manager',
            ),
        ),
    ]
