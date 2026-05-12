from decimal import Decimal, InvalidOperation

from django.db.models import F, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce

from store.models import Product, ProductVariant


class CatalogQueryService:
    """Query-сервис каталога и его производных представлений."""

    @staticmethod
    def base_queryset():
        return (
            Product.objects.filter(is_on_sale=True)
            .select_related("category")
            .prefetch_related(
                "images",
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.select_related("image").order_by("price", "id"),
                ),
            )
        )

    @staticmethod
    def normalize_price_filter(value):
        if value in (None, ""):
            return None
        try:
            price = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
        if price < 0:
            return None
        return price

    @classmethod
    def build_product_list_queryset(
        cls,
        query: str = "",
        category_id: str = "",
        sort: str = "",
        size: str = "",
        in_stock: bool = False,
        price_min: str = "",
        price_max: str = "",
    ):
        queryset = cls.base_queryset()
        needs_distinct = False

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(short_description__icontains=query)
                | Q(description__icontains=query)
                | Q(variants__sku__icontains=query)
            )
            needs_distinct = True

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        normalized_price_min = cls.normalize_price_filter(price_min)
        normalized_price_max = cls.normalize_price_filter(price_max)
        variant_filter = Q()
        has_variant_filter = False
        if size:
            variant_filter &= Q(variants__size=size)
            has_variant_filter = True
        if in_stock:
            variant_filter &= Q(variants__quantity__gt=F("variants__reserved_quantity"))
            has_variant_filter = True
        if normalized_price_min is not None:
            variant_filter &= Q(variants__price__gte=normalized_price_min)
            has_variant_filter = True
        if normalized_price_max is not None:
            variant_filter &= Q(variants__price__lte=normalized_price_max)
            has_variant_filter = True
        if has_variant_filter:
            queryset = queryset.filter(variant_filter)
            needs_distinct = True

        if needs_distinct:
            queryset = queryset.distinct()

        if sort in {"price_asc", "price_desc"}:
            # Используем conditional aggregation чтобы избежать влияния фильтрации по variants__sku
            queryset = queryset.annotate(
                min_available_variant_price=Min(
                    "variants__price",
                    filter=Q(variants__quantity__gt=F("variants__reserved_quantity")),
                ),
                # Coalesce с Min("variants__price") может быть затронут фильтрацией,
                # но это менее критично для сортировки по цене
                min_variant_price=Coalesce("min_available_variant_price", Min("variants__price")),
            )

        if sort == "price_asc":
            return queryset.order_by("min_variant_price", "name", "id")
        if sort == "price_desc":
            return queryset.order_by("-min_variant_price", "name", "id")
        if sort == "name_asc":
            return queryset.order_by("name", "id")
        if sort == "name_desc":
            return queryset.order_by("-name", "id")

        queryset = queryset.annotate(
            popularity_score=Coalesce(Sum("variants__order_items__quantity"), Value(0)),
        )
        return queryset.order_by("-popularity_score", "-created_at", "id")

    @classmethod
    def build_popular_products_queryset(cls):
        return cls.base_queryset().order_by("-created_at")

    @staticmethod
    def build_available_sizes_queryset():
        return (
            ProductVariant.objects.filter(product__is_on_sale=True)
            .exclude(size__isnull=True)
            .exclude(size="")
            .order_by("size")
            .values_list("size", flat=True)
            .distinct()
        )
