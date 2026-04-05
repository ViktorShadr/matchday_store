from django.core.validators import MinValueValidator
from django.conf import settings
from django.db import models


class Address(models.Model):
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
        verbose_name = "Адрес"
        verbose_name_plural = "Адреса"
        ordering = ["-is_default", "-updated_at", "-created_at"]

    def __str__(self):
        return f"{self.recipient_name} - {self.city}, {self.street}, {self.house}"


class Order(models.Model):
    class Status(models.TextChoices):
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
        PENDING = "pending", "Ожидает оплаты"
        REQUIRES_ACTION = "requires_action", "Требует действия"
        SUCCEEDED = "succeeded", "Успешно"
        FAILED = "failed", "Ошибка"
        CANCELLED = "cancelled", "Отменен"
        REFUNDED = "refunded", "Возвращен"

    class FulfillmentStatus(models.TextChoices):
        NEW = "new", "Новый"
        RESERVED = "reserved", "Зарезервирован"
        PACKING = "packing", "Комплектуется"
        SHIPPED = "shipped", "Отправлен"
        DELIVERED = "delivered", "Доставлен"
        RETURNED = "returned", "Возвращен"
        CANCELLED = "cancelled", "Отменен"

    class DeliveryMethod(models.TextChoices):
        COURIER = "courier", "Курьер"
        PICKUP = "pickup", "Самовывоз"
        PVZ = "pvz", "Пункт выдачи"

    number = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
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
        default=DeliveryMethod.COURIER,
    )
    delivery_address = models.ForeignKey(
        "orders.Address",
        on_delete=models.PROTECT,
        related_name="orders",
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
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ {self.number}"


class OrderItem(models.Model):
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
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity}"
