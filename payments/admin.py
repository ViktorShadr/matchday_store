from django.contrib import admin

from payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "provider", "status", "amount", "currency", "paid_at", "created_at")
    list_filter = ("provider", "status", "currency", "created_at")
    search_fields = ("idempotency_key", "provider_payment_id", "order__number", "order__email")
    autocomplete_fields = ("order",)
    readonly_fields = ("created_at", "updated_at")
