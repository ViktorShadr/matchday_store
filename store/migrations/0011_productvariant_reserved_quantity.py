from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0010_seed_cms_content"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="reserved_quantity",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("quantity")),
                name="product_variant_reserved_lte_quantity",
            ),
        ),
    ]
