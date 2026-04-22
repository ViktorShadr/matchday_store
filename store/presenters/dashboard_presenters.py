from django.utils import timezone

from orders.models import Order


class WarehouseProductPresenter:
    """Презентация продуктов складского dashboard."""

    @staticmethod
    def format_variant_label(variant_count: int) -> str:
        if variant_count % 10 == 1 and variant_count % 100 != 11:
            word = "вариант"
        elif variant_count % 10 in (2, 3, 4) and variant_count % 100 not in (12, 13, 14):
            word = "варианта"
        else:
            word = "вариантов"
        return f"{variant_count} {word}"

    @staticmethod
    def resolve_stock_state(stock_total: int) -> tuple[str, str]:
        if stock_total <= 0:
            return "out", "Нет в наличии"
        if stock_total < 5:
            return "low", f"Мало осталось: {stock_total}"
        return "in", f"В наличии: {stock_total}"

    @classmethod
    def present_many(cls, products):
        prepared_products = []
        for product in products:
            product.preview_image = next(iter(product.images.all()), None)
            product.sku = f"SKU-{product.pk}"
            product.variant_label = cls.format_variant_label(product.variant_count)
            stock_total = int(product.stock_total or 0)
            product.stock_total = stock_total
            product.stock_state, product.stock_label = cls.resolve_stock_state(stock_total)
            prepared_products.append(product)
        return prepared_products


class DashboardOrderPresenter:
    """Презентация заказа для staff-dashboard."""

    STATUS_CHOICES = (
        ("new", "Новый"),
        ("processing", "В обработке"),
        ("ready", "Готов к выдаче"),
        ("issued", "Выдан"),
        ("cancelled", "Отменен"),
    )
    STATUS_FILTERS = (
        ("all", "Все"),
        ("new", "Новые"),
        ("processing", "В обработке"),
        ("ready", "Готов к выдаче"),
        ("issued", "Выдан"),
        ("cancelled", "Отменен"),
    )
    STATUS_META = {
        "new": {"label": "Новый", "badge_class": "sf-status-badge sf-status-badge--warning"},
        "processing": {"label": "В обработке", "badge_class": "sf-status-badge sf-status-badge--info"},
        "ready": {"label": "Готов к выдаче", "badge_class": "sf-status-badge sf-status-badge--success"},
        "issued": {"label": "Выдан", "badge_class": "sf-status-badge sf-status-badge--dark"},
        "cancelled": {"label": "Отменен", "badge_class": "sf-status-badge sf-status-badge--danger"},
    }
    FINAL_STATUS_KEYS = frozenset({"issued", "cancelled"})
    PAYMENT_STATUS_CHOICES = (
        (Order.PaymentStatus.PENDING, "Ожидает оплаты"),
        (Order.PaymentStatus.SUCCEEDED, "Оплачен"),
        (Order.PaymentStatus.FAILED, "Ошибка оплаты"),
        (Order.PaymentStatus.CANCELLED, "Оплата отменена"),
        (Order.PaymentStatus.REFUNDED, "Возврат выполнен"),
    )
    PAYMENT_STATUS_META = {
        Order.PaymentStatus.PENDING: {"label": "Ожидает оплаты", "badge_class": "sf-status-badge sf-status-badge--warning"},
        Order.PaymentStatus.SUCCEEDED: {"label": "Оплачен", "badge_class": "sf-status-badge sf-status-badge--success"},
        Order.PaymentStatus.FAILED: {"label": "Ошибка оплаты", "badge_class": "sf-status-badge sf-status-badge--danger"},
        Order.PaymentStatus.CANCELLED: {"label": "Оплата отменена", "badge_class": "sf-status-badge sf-status-badge--dark"},
        Order.PaymentStatus.REFUNDED: {"label": "Возврат выполнен", "badge_class": "sf-status-badge sf-status-badge--info"},
    }

    @classmethod
    def get_status_key(cls, order: Order) -> str:
        if order.status == Order.Status.CANCELLED or order.fulfillment_status == Order.FulfillmentStatus.CANCELLED:
            return "cancelled"
        if order.fulfillment_status == Order.FulfillmentStatus.DELIVERED:
            return "issued"
        if order.fulfillment_status == Order.FulfillmentStatus.RESERVED:
            return "ready"
        if order.fulfillment_status in {Order.FulfillmentStatus.PACKING, Order.FulfillmentStatus.SHIPPED}:
            return "processing"
        return "new"

    @classmethod
    def get_payment_meta(cls, order: Order) -> dict:
        return cls.PAYMENT_STATUS_META.get(
            order.payment_status,
            cls.PAYMENT_STATUS_META[Order.PaymentStatus.PENDING],
        )

    @classmethod
    def apply_status(cls, order: Order, status_key: str) -> None:
        if status_key == "new":
            order.fulfillment_status = Order.FulfillmentStatus.NEW
            order.status = Order.Status.PLACED
            order.cancelled_at = None
            return
        if status_key == "processing":
            order.fulfillment_status = Order.FulfillmentStatus.PACKING
            order.status = Order.Status.PROCESSING
            order.cancelled_at = None
            return
        if status_key == "ready":
            order.fulfillment_status = Order.FulfillmentStatus.RESERVED
            order.status = Order.Status.PROCESSING
            order.cancelled_at = None
            return
        if status_key == "issued":
            order.fulfillment_status = Order.FulfillmentStatus.DELIVERED
            order.status = Order.Status.DELIVERED
            order.cancelled_at = None
            return
        if status_key == "cancelled":
            order.fulfillment_status = Order.FulfillmentStatus.CANCELLED
            order.status = Order.Status.CANCELLED
            if order.cancelled_at is None:
                order.cancelled_at = timezone.now()
            return
        raise ValueError(f"Unsupported dashboard status: {status_key}")

    @classmethod
    def present(cls, order: Order) -> Order:
        dashboard_status_key = cls.get_status_key(order)
        dashboard_status_meta = cls.STATUS_META[dashboard_status_key]
        payment_status_meta = cls.get_payment_meta(order)
        order.dashboard_status_key = dashboard_status_key
        order.dashboard_status_label = dashboard_status_meta["label"]
        order.dashboard_status_badge = dashboard_status_meta["badge_class"]
        order.dashboard_payment_label = payment_status_meta["label"]
        order.dashboard_payment_badge = payment_status_meta["badge_class"]
        return order

    @classmethod
    def present_many(cls, orders):
        return [cls.present(order) for order in orders]
