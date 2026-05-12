from django.contrib import admin

from orders.models import Address, Order, OrderItem, OrderStatusTransition


class OrderItemInline(admin.TabularInline):
    """Класс OrderItemInline."""

    model = OrderItem
    extra = 0
    autocomplete_fields = ("product_variant",)


class OrderStatusTransitionInline(admin.TabularInline):
    model = OrderStatusTransition
    extra = 0
    can_delete = False
    fields = ("transition_type", "from_value", "to_value", "changed_by", "created_at")
    readonly_fields = fields
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Address."""

    list_display = (
        "id",
        "recipient_name",
        "user",
        "phone",
        "city",
        "street",
        "house",
        "postal_code",
        "is_default",
        "updated_at",
    )
    list_filter = ("country", "city", "is_default", "created_at", "updated_at")
    search_fields = ("recipient_name", "phone", "city", "street", "postal_code", "user__email")
    ordering = ("-is_default", "-updated_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Order."""

    inlines = (OrderItemInline, OrderStatusTransitionInline)
    list_display = (
        "id",
        "number",
        "recipient_name",
        "user",
        "email",
        "phone",
        "status",
        "payment_status",
        "fulfillment_status",
        "delivery_method",
        "total_amount",
        "currency",
        "issued_at",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_status",
        "fulfillment_status",
        "delivery_method",
        "currency",
        "created_at",
    )
    search_fields = ("number", "recipient_name", "email", "phone", "user__email", "pickup_point_code", "staff_note")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "confirmed_at", "paid_at", "issued_at", "cancelled_at")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для OrderItem."""

    list_display = (
        "id",
        "order",
        "product_name_snapshot",
        "product_variant",
        "unit_price",
        "quantity",
        "line_total",
        "created_at",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = ("order__number", "product_name_snapshot", "sku_snapshot")
    ordering = ("order", "id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrderStatusTransition)
class OrderStatusTransitionAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "transition_type", "from_value", "to_value", "changed_by", "created_at")
    list_filter = ("transition_type", "created_at")
    search_fields = ("order__number", "from_value", "to_value", "changed_by__email")
    ordering = ("-created_at", "-id")
    readonly_fields = ("order", "transition_type", "from_value", "to_value", "changed_by", "created_at")
