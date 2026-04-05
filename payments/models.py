from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    class Provider(models.TextChoices):
        MANUAL = "manual", "Ручная оплата"
        YOOKASSA = "yookassa", "YooKassa"
        STRIPE = "stripe", "Stripe"
        CLOUDPAYMENTS = "cloudpayments", "CloudPayments"

    class Status(models.TextChoices):
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
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Платеж {self.id} для заказа {self.order.number}"
