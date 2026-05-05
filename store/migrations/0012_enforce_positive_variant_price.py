from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0011_productvariant_reserved_quantity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productvariant",
            name="price",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="product_variant_price_gt_zero",
            ),
        ),
    ]
