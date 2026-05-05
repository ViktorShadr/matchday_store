from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_orderitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="recipient_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_address",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="orders",
                to="orders.address",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_method",
            field=models.CharField(
                choices=[("courier", "Курьер"), ("pickup", "Самовывоз"), ("pvz", "Пункт выдачи")],
                default="pickup",
                max_length=32,
            ),
        ),
    ]
