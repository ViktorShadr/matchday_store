from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Address(models.Model):
    """
    Модель адреса доставки пользователя.

    Хранит информацию об адресах доставки пользователей.
    Может быть несколько адресов на одного пользователя.

    Attributes:
        user (User): Владелец адреса
        recipient_name (str): ФИО получателя
        phone (str): Номер телефона получателя
        country (str): Страна
        city (str): Город
        postal_code (str): Почтовый индекс
        street (str): Улица
        house (str): Номер дома
        building (str): Корпус (опционально)
        apartment (str): Номер квартиры (опционально)
        comment (str): Комментарий к адресу (опционально)
        is_default (bool): Флаг адреса по умолчанию
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    recipient_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    country = models.CharField(max_length=100, default="Россия")
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    street = models.CharField(max_length=255)
    house = models.CharField(max_length=50)
    building = models.CharField(max_length=50, blank=True)
    apartment = models.CharField(max_length=50, blank=True)
    comment = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Адрес"
        verbose_name_plural = "Адреса"
        ordering = ["-is_default", "-updated_at", "-created_at"]

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return f"{self.recipient_name} - {self.city}, {self.street}, {self.house}"


class Order(models.Model):
    """
    Модель заказа в системе.

    Представляет полный заказ пользователя со статусом оплаты,
    доставки и исполнения.

    Attributes:
        number (str): Уникальный номер заказа
        user (User): Пользователь, сделавший заказ
        email (str): Email заказчика
        phone (str): Номер телефона заказчика
        status (str): Статус заказа (из Status.choices)
        payment_status (str): Статус оплаты (из PaymentStatus.choices)
        fulfillment_status (str): Статус исполнения (из FulfillmentStatus.choices)
        delivery_method (str): Способ доставки (из DeliveryMethod.choices)
        delivery_address (Address): Адрес доставки
        pickup_point_code (str): Код пункта выдачи (для самовывоза)
        subtotal_amount (Decimal): Сумма товаров
        delivery_amount (Decimal): Стоимость доставки
        discount_amount (Decimal): Сумма скидки
        total_amount (Decimal): Итоговая сумма
        currency (str): Валюта
        customer_comment (str): Комментарий заказчика
        source_cart_id (int): ID корзины-источника
        confirmed_at (datetime): Дата подтверждения
        paid_at (datetime): Дата оплаты
        issued_at (datetime): Дата выдачи заказа
        cancelled_at (datetime): Дата отмены
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    class Status(models.TextChoices):
        """Класс статусов заказа."""

        DRAFT = "draft", "Черновик"
        PLACED = "placed", "Оформлен"
        AWAITING_PAYMENT = "awaiting_payment", "Ожидает оплаты"
        PAID = "paid", "Оплачен"
        PROCESSING = "processing", "В обработке"
        SHIPPED = "shipped", "Отправлен"
        DELIVERED = "delivered", "Доставлен"
        CANCELLED = "cancelled", "Отменен"
        REFUNDED = "refunded", "Возвращен"

    class PaymentStatus(models.TextChoices):
        """Класс статусов оплаты заказа."""

        PENDING = "pending", "Ожидает оплаты"
        REQUIRES_ACTION = "requires_action", "Требует действия"
        SUCCEEDED = "succeeded", "Успешно"
        FAILED = "failed", "Ошибка"
        CANCELLED = "cancelled", "Отменен"
        REFUNDED = "refunded", "Возвращен"

    class FulfillmentStatus(models.TextChoices):
        """Класс статусов исполнения заказа."""

        NEW = "new", "Новый"
        RESERVED = "reserved", "Зарезервирован"
        PACKING = "packing", "Комплектуется"
        SHIPPED = "shipped", "Отправлен"
        DELIVERED = "delivered", "Доставлен"
        RETURNED = "returned", "Возвращен"
        CANCELLED = "cancelled", "Отменен"

    class DeliveryMethod(models.TextChoices):
        """Класс способов доставки."""

        COURIER = "courier", "Курьер"
        PICKUP = "pickup", "Самовывоз"
        PVZ = "pvz", "Пункт выдачи"

    number = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    recipient_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(
        max_length=32,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    fulfillment_status = models.CharField(
        max_length=32,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.NEW,
    )
    delivery_method = models.CharField(
        max_length=32,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.PICKUP,
    )
    delivery_address = models.ForeignKey(
        "orders.Address",
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
    )
    pickup_point_code = models.CharField(max_length=100, blank=True)
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="RUB")
    customer_comment = models.TextField(blank=True)
    source_cart_id = models.PositiveBigIntegerField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return f"Заказ {self.number}"


class OrderStatusTransition(models.Model):
    """Журнал переходов статусов заказа."""

    class TransitionType(models.TextChoices):
        DASHBOARD_STATUS = "dashboard_status", "Статус dashboard"
        ORDER_STATUS = "order_status", "Статус заказа"
        FULFILLMENT_STATUS = "fulfillment_status", "Статус исполнения"
        PAYMENT_STATUS = "payment_status", "Статус оплаты"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="status_transitions")
    transition_type = models.CharField(max_length=32, choices=TransitionType.choices)
    from_value = models.CharField(max_length=64)
    to_value = models.CharField(max_length=64)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="order_status_transitions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Переход статуса заказа"
        verbose_name_plural = "Переходы статусов заказа"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.order.number}: {self.transition_type} {self.from_value} -> {self.to_value}"

    @classmethod
    def log_if_changed(
        cls,
        *,
        order: "Order",
        transition_type: str,
        from_value: str | None,
        to_value: str | None,
        changed_by=None,
    ):
        normalized_from = "" if from_value is None else str(from_value)
        normalized_to = "" if to_value is None else str(to_value)
        if normalized_from == normalized_to:
            return None

        return cls.objects.create(
            order=order,
            transition_type=transition_type,
            from_value=normalized_from,
            to_value=normalized_to,
            changed_by=changed_by,
        )


class OrderItem(models.Model):
    """
    Модель элемента заказа.

    Представляет один товар в заказе с сохранением снимка информации
    на момент создания заказа.

    Attributes:
        order (Order): Заказ, содержащий этот товар
        product_variant (ProductVariant): Вариант товара
        product_name_snapshot (str): Название товара на момент заказа
        sku_snapshot (str): SKU товара на момент заказа
        size_snapshot (str): Размер товара на момент заказа
        color_snapshot (str): Цвет товара на момент заказа
        unit_price (Decimal): Цена единицы товара
        quantity (int): Количество товара в заказе
        line_total (Decimal): Итоговая сумма за товар
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(
        "store.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name_snapshot = models.CharField(max_length=255)
    sku_snapshot = models.CharField(max_length=100, blank=True)
    size_snapshot = models.CharField(max_length=50, blank=True)
    color_snapshot = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        ordering = ["id"]

    def __str__(self):
        """Возвращает строковое представление объекта."""
        return f"{self.product_name_snapshot} x {self.quantity}"
