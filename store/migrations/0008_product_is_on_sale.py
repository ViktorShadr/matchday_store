from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0007_alter_productvariant_color_alter_productvariant_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_on_sale",
            field=models.BooleanField(default=True),
        ),
    ]
