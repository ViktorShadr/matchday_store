from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    """
    Модель платежа в системе.

    Представляет запись о платеже или попытке платежа по заказу.
    Может быть несколько платежей по одному заказу.

    Attributes:
        order (Order): Заказ, по которому осуществляется платеж
        provider (str): Поставщик платежа (из Provider.choices)
        provider_payment_id (str): ID платежа у поставщика
        idempotency_key (str): Ключ идемпотентности платежа
        status (str): Статус платежа (из Status.choices)
        amount (Decimal): Сумма платежа
        currency (str): Валюта платежа
        raw_request (dict): Сырой запрос к платежной системе
        raw_response (dict): Сырой ответ от платежной системы
        failure_reason (str): Причина отказа (если есть)
        paid_at (datetime): Дата успешной оплаты
        refunded_amount (Decimal): Сумма возврата
        created_at (datetime): Дата создания
        updated_at (datetime): Дата последнего обновления
    """

    class Provider(models.TextChoices):
        """Класс поставщиков платежей."""

        MANUAL = "manual", "Ручная оплата"
        YOOKASSA = "yookassa", "YooKassa"
        STRIPE = "stripe", "Stripe"
        CLOUDPAYMENTS = "cloudpayments", "CloudPayments"

    class Status(models.TextChoices):
        """Класс статусов платежа."""

        PENDING = "pending", "Ожидает оплаты"
        REQUIRES_ACTION = "requires_action", "Требует действия"
        SUCCEEDED = "succeeded", "Успешно"
        FAILED = "failed", "Ошибка"
        CANCELLED = "cancelled", "Отменен"
        REFUNDED = "refunded", "Возвращен"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.MANUAL)
    provider_payment_id = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="RUB")
    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Мета-настройки класса."""

        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self):
        """Возвращает строковое представление платежа."""
        return f"Платеж {self.id} для заказа {self.order.number}"
