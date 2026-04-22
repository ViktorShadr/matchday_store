from django.db.models import Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce

from store.models import Product, ProductVariant


class CatalogQueryService:
    """Query-сервис каталога и его производных представлений."""

    @staticmethod
    def base_queryset():
        return Product.objects.select_related("category").prefetch_related(
            "images",
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.select_related("image").order_by("price", "id"),
            ),
        )

    @classmethod
    def build_product_list_queryset(cls, query: str = "", category_id: str = "", sort: str = ""):
        queryset = cls.base_queryset()

        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        if sort in {"price_asc", "price_desc"}:
            queryset = queryset.annotate(
                min_available_variant_price=Min("variants__price", filter=Q(variants__quantity__gt=0)),
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
