from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0010_guest_order_access_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_session_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Guest checkout session snapshot for stock reservation abuse limits.",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="checkout_ip_address",
            field=models.GenericIPAddressField(
                blank=True,
                db_index=True,
                help_text="Guest checkout IP snapshot for stock reservation abuse limits.",
                null=True,
            ),
        ),
    ]
