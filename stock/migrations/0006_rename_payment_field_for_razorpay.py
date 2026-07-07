# Generated manually - switches Payment's payment-gateway identifier from Stripe to Razorpay

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0005_payment'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payment',
            old_name='stripe_session_id',
            new_name='razorpay_order_id',
        ),
        migrations.AddField(
            model_name='payment',
            name='razorpay_payment_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
