from django.contrib import admin

from .models import Cart, CartItem, Category, InfoCard, Page, Product, ProductImage, ProductVariant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Category."""

    list_display = ["name", "created_at", "updated_at"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Product."""

    list_display = ["name", "category", "old_price", "is_on_sale", "created_at", "updated_at"]
    list_filter = ["category", "is_on_sale", "created_at"]
    search_fields = ["name", "short_description", "description", "material"]
    ordering = ["name"]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для ProductVariant."""

    list_display = ["product", "sku", "size", "color", "price", "quantity", "reserved_quantity", "available_quantity"]
    list_filter = ["size", "color", "product"]
    search_fields = ["product__name", "sku", "size", "color"]
    ordering = ["product", "size", "color"]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для ProductImage."""

    list_display = ["product", "alt_text", "is_primary", "created_at"]
    list_filter = ["is_primary", "product"]
    search_fields = ["product__name", "alt_text"]
    ordering = ["-created_at"]


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Page."""

    list_display = ["title", "slug", "is_published", "updated_by", "updated_at", "created_at"]
    search_fields = ["title", "slug", "lead", "content"]
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ["is_published", "updated_at", "created_at"]
    ordering = ["slug"]
    readonly_fields = ["created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        """Проставляет автора последнего обновления страницы."""
        if request.user and request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(InfoCard)
class InfoCardAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для InfoCard."""

    list_display = ["title", "icon", "sort_order", "is_published", "updated_at"]
    search_fields = ["title", "text", "icon"]
    list_filter = ["is_published", "updated_at", "created_at"]
    ordering = ["sort_order", "id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для Cart."""

    list_display = ["user", "total_items", "total_price", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    ordering = ["-updated_at"]
    readonly_fields = ["created_at", "updated_at"]

    def total_items(self, obj):
        """Возвращает общее количество товаров."""
        return obj.total_items

    total_items.short_description = "Количество товаров"

    def total_price(self, obj):
        """Возвращает общую стоимость."""
        return f"{obj.total_price:.2f} ₽"

    total_price.short_description = "Общая стоимость"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для CartItem."""

    list_display = ["cart", "product_variant", "quantity", "total_price", "created_at"]
    list_filter = ["created_at", "product_variant__product"]
    search_fields = ["cart__user__email", "product_variant__product__name"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    def total_price(self, obj):
        """Возвращает общую стоимость."""
        return f"{obj.total_price:.2f} ₽"

    total_price.short_description = "Общая стоимость"
