from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0012_enforce_positive_variant_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="care_instructions",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="product",
            name="material",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="old_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="short_description",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="size_guide",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="sku",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                condition=~models.Q(sku=""),
                fields=("sku",),
                name="unique_nonblank_product_variant_sku",
            ),
        ),
    ]
