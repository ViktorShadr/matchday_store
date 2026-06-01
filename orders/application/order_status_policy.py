from django.utils import timezone

from orders.models import Order


class OrderStatusPolicy:
    """Доменная политика staff-статусов заказа."""

    STATUS_KEYS = ("new", "processing", "ready", "issued", "cancelled")
    FINAL_STATUS_KEYS = frozenset({"issued", "cancelled"})
    RESERVE_TERMINAL_ORDER_STATUSES = frozenset(
        {
            Order.Status.CANCELLED,
            Order.Status.DELIVERED,
            Order.Status.REFUNDED,
        }
    )
    RESERVE_TERMINAL_FULFILLMENT_STATUSES = frozenset(
        {
            Order.FulfillmentStatus.CANCELLED,
            Order.FulfillmentStatus.DELIVERED,
            Order.FulfillmentStatus.RETURNED,
        }
    )
    STATUS_TRANSITIONS = {
        "new": frozenset({"new", "processing", "ready", "cancelled"}),
        "processing": frozenset({"processing", "ready", "cancelled"}),
        "ready": frozenset({"ready", "processing", "issued", "cancelled"}),
        "issued": frozenset({"issued"}),
        "cancelled": frozenset({"cancelled"}),
    }

    @classmethod
    def is_valid_status_key(cls, status_key: str) -> bool:
        return status_key in cls.STATUS_TRANSITIONS

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
    def get_allowed_transitions(cls, status_key: str) -> frozenset[str]:
        return cls.STATUS_TRANSITIONS[status_key]

    @classmethod
    def is_final_status_key(cls, status_key: str) -> bool:
        return status_key in cls.FINAL_STATUS_KEYS

    @classmethod
    def reserve_relevant_queryset(cls, queryset):
        return queryset.exclude(status__in=cls.RESERVE_TERMINAL_ORDER_STATUSES).exclude(
            fulfillment_status__in=cls.RESERVE_TERMINAL_FULFILLMENT_STATUSES
        )

    @classmethod
    def can_transition(cls, current_status: str, next_status: str) -> bool:
        return next_status in cls.get_allowed_transitions(current_status)

    @staticmethod
    def can_issue(order: Order) -> bool:
        return order.payment_status == Order.PaymentStatus.SUCCEEDED

    @classmethod
    def apply_status(cls, order: Order, status_key: str) -> None:
        if status_key == "new":
            order.fulfillment_status = Order.FulfillmentStatus.NEW
            order.status = Order.Status.PLACED
            order.issued_at = None
            order.cancelled_at = None
            return
        if status_key == "processing":
            order.fulfillment_status = Order.FulfillmentStatus.PACKING
            order.status = Order.Status.PROCESSING
            order.issued_at = None
            order.cancelled_at = None
            return
        if status_key == "ready":
            order.fulfillment_status = Order.FulfillmentStatus.RESERVED
            order.status = Order.Status.PROCESSING
            order.issued_at = None
            order.cancelled_at = None
            return
        if status_key == "issued":
            order.fulfillment_status = Order.FulfillmentStatus.DELIVERED
            order.status = Order.Status.DELIVERED
            if order.issued_at is None:
                order.issued_at = timezone.now()
            order.cancelled_at = None
            return
        if status_key == "cancelled":
            order.fulfillment_status = Order.FulfillmentStatus.CANCELLED
            order.status = Order.Status.CANCELLED
            order.issued_at = None
            if order.cancelled_at is None:
                order.cancelled_at = timezone.now()
            return
        raise ValueError(f"Unsupported dashboard status: {status_key}")
