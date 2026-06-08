from decimal import Decimal, InvalidOperation

from django.db.models import Count, F, IntegerField, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date

from orders.models import Order, OrderItem
from store.models import Category, Product, ProductImage, ProductVariant


class WarehouseQueryService:
    """Query-сервис складского dashboard."""

    SORT_OPTIONS = {
        "updated_desc": ("-updated_at",),
        "name_asc": ("name",),
        "name_desc": ("-name",),
        "stock_desc": ("-available_stock_total", "name"),
        "stock_asc": ("available_stock_total", "name"),
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

        base_queryset = Product.objects.select_related("category")

        if search_query:
            variant_filter = Q(sku__icontains=search_query)
            normalized_search_query = search_query.lower()
            if normalized_search_query.startswith("sku-"):
                normalized_search_query = normalized_search_query[4:]

            search_filter = Q(name__icontains=search_query)
            if normalized_search_query.isdigit():
                numeric_query = int(normalized_search_query)
                search_filter |= Q(pk=numeric_query)
                variant_filter |= Q(pk=numeric_query)

            matching_variant_product_ids = ProductVariant.objects.filter(variant_filter).values("product_id")
            search_filter |= Q(pk__in=matching_variant_product_ids)
            base_queryset = base_queryset.filter(search_filter)

        queryset = base_queryset.prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("-is_primary", "-created_at"),
            ),
            Prefetch("variants", queryset=ProductVariant.objects.order_by("pk")),
        ).annotate(
            variant_count=Count("variants", distinct=True),
            stock_total=Coalesce(Sum("variants__quantity"), 0),
            reserved_stock_total=Coalesce(Sum("variants__reserved_quantity"), 0),
            available_stock_total=Coalesce(
                Sum(F("variants__quantity") - F("variants__reserved_quantity")),
                0,
                output_field=IntegerField(),
            ),
            min_price=Coalesce(Min("variants__price"), Value(Decimal("0.00"))),
        )

        if selected_category.isdigit():
            queryset = queryset.filter(category_id=int(selected_category))

        if selected_stock_filter == "in_stock":
            queryset = queryset.filter(available_stock_total__gt=0)
        elif selected_stock_filter == "low_stock":
            queryset = queryset.filter(available_stock_total__gt=0, available_stock_total__lt=5)
        elif selected_stock_filter == "out_of_stock":
            queryset = queryset.filter(available_stock_total=0)

        return queryset.order_by(*cls.SORT_OPTIONS[selected_sort])

    @staticmethod
    def build_categories_queryset():
        return Category.objects.annotate(product_count=Count("products")).order_by("name")


class DashboardOrderQueryService:
    """Query-сервис заказов в staff-dashboard."""

    STATUS_KEYS = frozenset({"new", "processing", "ready", "issued", "cancelled"})
    ALL_FILTERS = frozenset({"all", *STATUS_KEYS})
    PAYMENT_STATUS_FILTERS = frozenset({"", *Order.PaymentStatus.values})

    @staticmethod
    def apply_status_filter(queryset, status_filter: str):
        if status_filter == "new":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.NEW)
        if status_filter == "processing":
            return queryset.filter(
                fulfillment_status__in=(Order.FulfillmentStatus.PACKING, Order.FulfillmentStatus.SHIPPED)
            )
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
    def normalize_payment_status_filter(cls, payment_status_filter: str) -> str:
        if payment_status_filter in cls.PAYMENT_STATUS_FILTERS:
            return payment_status_filter
        return ""

    @staticmethod
    def normalize_amount_filter(value: str):
        if not value:
            return None
        try:
            amount = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
        if amount < 0:
            return None
        return amount

    @classmethod
    def build_orders_queryset(
        cls,
        status_filter: str = "all",
        search_query: str = "",
        payment_status_filter: str = "",
        created_from: str = "",
        created_to: str = "",
        amount_min: str = "",
        amount_max: str = "",
    ):
        queryset = Order.objects.select_related("user").annotate(items_count=Count("items")).order_by("-created_at")
        if search_query:
            search_filter = (
                Q(number__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(phone__icontains=search_query)
                | Q(recipient_name__icontains=search_query)
            )
            digits_query = "".join(char for char in search_query if char.isdigit())
            if digits_query:
                search_filter |= Q(phone__icontains=digits_query)
            queryset = queryset.filter(search_filter)
        if payment_status_filter:
            queryset = queryset.filter(payment_status=payment_status_filter)
        created_from_date = parse_date(created_from) if created_from else None
        created_to_date = parse_date(created_to) if created_to else None
        if created_from_date:
            queryset = queryset.filter(created_at__date__gte=created_from_date)
        if created_to_date:
            queryset = queryset.filter(created_at__date__lte=created_to_date)
        normalized_amount_min = cls.normalize_amount_filter(amount_min)
        normalized_amount_max = cls.normalize_amount_filter(amount_max)
        if normalized_amount_min is not None:
            queryset = queryset.filter(total_amount__gte=normalized_amount_min)
        if normalized_amount_max is not None:
            queryset = queryset.filter(total_amount__lte=normalized_amount_max)
        return cls.apply_status_filter(queryset, status_filter)


class WarehouseReservationQueryService:
    """Query-сервис активных заказов, удерживающих складской резерв."""

    @classmethod
    def get_active_reservation_items_by_variant(cls, variants) -> dict[int, list[OrderItem]]:
        from orders.application.order_status_policy import OrderStatusPolicy

        variant_ids = [variant.pk for variant in variants]
        if not variant_ids:
            return {}

        reservation_items = (
            OrderItem.objects.select_related("order")
            .filter(product_variant_id__in=variant_ids)
            .exclude(order__status__in=OrderStatusPolicy.RESERVE_TERMINAL_ORDER_STATUSES)
            .exclude(order__fulfillment_status__in=OrderStatusPolicy.RESERVE_TERMINAL_FULFILLMENT_STATUSES)
            .order_by("order__created_at", "pk")
        )
        items_by_variant: dict[int, list[OrderItem]] = {variant_id: [] for variant_id in variant_ids}
        for item in reservation_items:
            items_by_variant.setdefault(item.product_variant_id, []).append(item)
        return items_by_variant
