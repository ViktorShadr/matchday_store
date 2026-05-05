from typing import List

from django.db.models import QuerySet

from store.models import ProductVariant
from store.repositories.interfaces import IProductVariantRepository


class ProductVariantRepository(IProductVariantRepository):
    """Реализация репозитория для работы с вариантами товаров."""

    def get_variant_for_update(self, variant_id: int) -> ProductVariant:
        """Получить вариант товара с блокировкой для обновления."""
        return ProductVariant.objects.select_for_update().select_related("product").get(id=variant_id)

    def get_variants_for_update(self, variant_ids: List[int]) -> QuerySet[ProductVariant]:
        """Получить варианты товаров с блокировкой для обновления."""
        return (
            ProductVariant.objects.select_for_update()
            .filter(id__in=variant_ids)
            .select_related("product")
            .order_by("pk")
        )
