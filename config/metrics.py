from prometheus_client import Counter, Gauge, Histogram

orders_placed_total = Counter(
    "orders_placed_total",
    "Total number of orders successfully placed",
)

orders_cancelled_total = Counter(
    "orders_cancelled_total",
    "Total number of orders cancelled",
    ["reason"],  # labels: 'customer', 'staff', 'expired'
)

orders_issued_total = Counter(
    "orders_issued_total",
    "Total number of orders issued (physical stock consumed)",
)

checkout_errors_total = Counter(
    "checkout_errors_total",
    "Total number of failed checkout attempts",
    ["reason"],  # labels: 'stock_unavailable', 'validation', 'duplicate'
)

checkout_duration_seconds = Histogram(
    "checkout_duration_seconds",
    "Duration of the checkout transaction in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

notifications_total = Counter(
    "order_notifications_total",
    "Total number of order email notifications by outcome",
    ["event", "status"],  # event: created/cancelled/..., status: sent/failed
)

stock_reserved_units = Gauge(
    "stock_reserved_units_total",
    "Total number of product units currently reserved across all variants",
)

payment_status_changes_total = Counter(
    "payment_status_changes_total",
    "Total number of payment status transitions",
    ["to_status"],  # labels: succeeded/failed/cancelled/refunded
)
