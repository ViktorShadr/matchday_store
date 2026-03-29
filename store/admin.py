from django.contrib import admin
from django.contrib.auth.models import Permission

from .models import Category, Product, ProductVariant, ProductImage


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
