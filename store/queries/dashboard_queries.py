from decimal import Decimal

from django.db.models import Count, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce

from orders.models import Order
from store.models import Category, Product, ProductImage


class WarehouseQueryService:
    """Query-сервис складского dashboard."""

    SORT_OPTIONS = {
        "updated_desc": ("-updated_at",),
        "name_asc": ("name",),
        "name_desc": ("-name",),
        "stock_desc": ("-stock_total", "name"),
        "stock_asc": ("stock_total", "name"),
        "price_asc": ("min_price", "name"),
        "price_desc": ("-min_price", "name"),
    }

    @classmethod
    def normalize_sort(cls, sort: str) -> str:
        if sort in cls.SORT_OPTIONS:
            return sort
        return "updated_desc"

    @classmethod
    def build_products_queryset(
        cls,
        search_query: str = "",
        selected_category: str = "",
        selected_stock_filter: str = "",
        selected_sort: str = "updated_desc",
    ):
        selected_sort = cls.normalize_sort(selected_sort)
        queryset = (
            Product.objects.select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "-created_at"),
                )
            )
            .annotate(
                variant_count=Count("variants", distinct=True),
                stock_total=Coalesce(Sum("variants__quantity"), 0),
                min_price=Coalesce(Min("variants__price"), Value(Decimal("0.00"))),
            )
        )

        if search_query:
            search_filter = Q(name__icontains=search_query)
            normalized_search_query = search_query.lower()
            if normalized_search_query.startswith("sku-"):
                normalized_search_query = normalized_search_query[4:]

            if normalized_search_query.isdigit():
                numeric_query = int(normalized_search_query)
                search_filter |= Q(pk=numeric_query) | Q(variants__pk=numeric_query)
            queryset = queryset.filter(search_filter).distinct()

        if selected_category.isdigit():
            queryset = queryset.filter(category_id=int(selected_category))

        if selected_stock_filter == "in_stock":
            queryset = queryset.filter(stock_total__gt=0)
        elif selected_stock_filter == "low_stock":
            queryset = queryset.filter(stock_total__gt=0, stock_total__lt=5)
        elif selected_stock_filter == "out_of_stock":
            queryset = queryset.filter(stock_total=0)

        return queryset.order_by(*cls.SORT_OPTIONS[selected_sort])

    @staticmethod
    def build_categories_queryset():
        return Category.objects.annotate(product_count=Count("products")).order_by("name")


class DashboardOrderQueryService:
    """Query-сервис заказов в staff-dashboard."""

    STATUS_KEYS = frozenset({"new", "processing", "ready", "issued", "cancelled"})
    ALL_FILTERS = frozenset({"all", *STATUS_KEYS})

    @staticmethod
    def apply_status_filter(queryset, status_filter: str):
        if status_filter == "new":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.NEW)
        if status_filter == "processing":
            return queryset.filter(fulfillment_status__in=(Order.FulfillmentStatus.PACKING, Order.FulfillmentStatus.SHIPPED))
        if status_filter == "ready":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.RESERVED)
        if status_filter == "issued":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.DELIVERED)
        if status_filter == "cancelled":
            return queryset.filter(
                Q(fulfillment_status=Order.FulfillmentStatus.CANCELLED) | Q(status=Order.Status.CANCELLED)
            )
        return queryset

    @classmethod
    def normalize_status_filter(cls, status_filter: str) -> str:
        if status_filter in cls.ALL_FILTERS:
            return status_filter
        return "all"

    @classmethod
    def build_orders_queryset(cls, status_filter: str = "all", search_query: str = ""):
        queryset = Order.objects.select_related("user").annotate(items_count=Count("items")).order_by("-created_at")
        if search_query:
            queryset = queryset.filter(Q(number__icontains=search_query) | Q(email__icontains=search_query))
        return cls.apply_status_filter(queryset, status_filter)
