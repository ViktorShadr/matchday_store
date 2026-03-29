from django.contrib import admin
from django.contrib.auth.models import Permission

from .models import Category, Product, ProductVariant, ProductImage, Cart, CartItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at', 'updated_at']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'created_at', 'updated_at']
    list_filter = ['category', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'size', 'color', 'price', 'quantity']
    list_filter = ['size', 'color', 'product']
    search_fields = ['product__name', 'size', 'color']
    ordering = ['product', 'size', 'color']


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'alt_text', 'is_primary', 'created_at']
    list_filter = ['is_primary', 'product']
    search_fields = ['product__name', 'alt_text']
    ordering = ['-created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_items', 'total_price', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    ordering = ['-updated_at']
    readonly_fields = ['created_at', 'updated_at']

    def total_items(self, obj):
        return obj.total_items

    total_items.short_description = 'Количество товаров'

    def total_price(self, obj):
        return f"{obj.total_price:.2f} ₽"

    total_price.short_description = 'Общая стоимость'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product_variant', 'quantity', 'total_price', 'created_at']
    list_filter = ['created_at', 'product_variant__product']
    search_fields = ['cart__user__email', 'product_variant__product__name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def total_price(self, obj):
        return f"{obj.total_price:.2f} ₽"

    total_price.short_description = 'Общая стоимость'
