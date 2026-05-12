from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_alter_order_user_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="staff_note",
            field=models.TextField(blank=True),
        ),
    ]
