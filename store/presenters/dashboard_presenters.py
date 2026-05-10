from orders.models import Order


def _order_status_policy():
    from orders.application.order_status_policy import OrderStatusPolicy

    return OrderStatusPolicy


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
    def resolve_stock_state(available_stock_total: int) -> tuple[str, str]:
        if available_stock_total <= 0:
            return "out", "Нет в наличии"
        if available_stock_total < 5:
            return "low", f"Доступно: {available_stock_total}"
        return "in", f"Доступно: {available_stock_total}"

    @classmethod
    def present_many(cls, products):
        prepared_products = []
        for product in products:
            product.preview_image = next(iter(product.images.all()), None)
            product.sku = f"SKU-{product.pk}"
            product.variant_label = cls.format_variant_label(product.variant_count)
            stock_total = int(product.stock_total or 0)
            reserved_stock_total = int(product.reserved_stock_total or 0)
            available_stock_total = int(product.available_stock_total or 0)
            product.stock_total = stock_total
            product.reserved_stock_total = reserved_stock_total
            product.available_stock_total = available_stock_total
            product.stock_state, product.stock_label = cls.resolve_stock_state(available_stock_total)
            product.stock_detail_label = f"Физически: {stock_total} / Резерв: {reserved_stock_total}"
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
    PAYMENT_STATUS_CHOICES = (
        (Order.PaymentStatus.PENDING, "Ожидает оплаты"),
        (Order.PaymentStatus.SUCCEEDED, "Оплачен"),
        (Order.PaymentStatus.FAILED, "Ошибка оплаты"),
        (Order.PaymentStatus.CANCELLED, "Оплата отменена"),
        (Order.PaymentStatus.REFUNDED, "Возврат выполнен"),
    )
    PAYMENT_STATUS_META = {
        Order.PaymentStatus.PENDING: {
            "label": "Ожидает оплаты",
            "badge_class": "sf-status-badge sf-status-badge--warning",
        },
        Order.PaymentStatus.SUCCEEDED: {"label": "Оплачен", "badge_class": "sf-status-badge sf-status-badge--success"},
        Order.PaymentStatus.FAILED: {
            "label": "Ошибка оплаты",
            "badge_class": "sf-status-badge sf-status-badge--danger",
        },
        Order.PaymentStatus.CANCELLED: {
            "label": "Оплата отменена",
            "badge_class": "sf-status-badge sf-status-badge--dark",
        },
        Order.PaymentStatus.REFUNDED: {
            "label": "Возврат выполнен",
            "badge_class": "sf-status-badge sf-status-badge--info",
        },
    }

    @classmethod
    def get_status_key(cls, order: Order) -> str:
        return _order_status_policy().get_status_key(order)

    @classmethod
    def get_payment_meta(cls, order: Order) -> dict:
        return cls.PAYMENT_STATUS_META.get(
            order.payment_status,
            cls.PAYMENT_STATUS_META[Order.PaymentStatus.PENDING],
        )

    @classmethod
    def get_available_status_choices(cls, order: Order) -> list[tuple[str, str, bool]]:
        current_status_key = cls.get_status_key(order)
        allowed_transitions = _order_status_policy().get_allowed_transitions(current_status_key)
        return [(value, label, value in allowed_transitions) for value, label in cls.STATUS_CHOICES]

    @classmethod
    def build_staff_guidance(cls, order: Order) -> list[str]:
        current_status_key = cls.get_status_key(order)
        guidance = []

        if current_status_key == "new":
            guidance.append("Проверьте состав заказа и подтвердите, что товар доступен к сборке.")
            guidance.append("Переведите заказ в «В обработке», когда сотрудник начал подготовку.")
        elif current_status_key == "processing":
            guidance.append("Заказ собирается. После комплектации переведите его в «Готов к выдаче».")
        elif current_status_key == "ready":
            guidance.append("Свяжитесь с клиентом и сообщите, что заказ готов к самовывозу.")
            if not _order_status_policy().can_issue(order):
                guidance.append("Перед выдачей подтвердите оплату через блок «Изменить оплату».")
            else:
                guidance.append("Оплата подтверждена. Заказ можно выдать клиенту.")
        elif current_status_key == "issued":
            guidance.append("Заказ уже выдан. Дальнейшие изменения через dashboard недоступны.")
        elif current_status_key == "cancelled":
            guidance.append("Заказ отменен. Остатки уже возвращены на склад автоматически.")

        if order.delivery_method == Order.DeliveryMethod.PICKUP:
            guidance.append("Сценарий MVP: самовывоз из магазина, доставка и онлайн-оплата не используются.")

        return guidance

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
