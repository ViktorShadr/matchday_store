from django.db import transaction

from orders.models import Order
from store.forms import ProductForm, VariantStockForm
from store.models import Category, Product, ProductVariant


class WarehouseDeleteProtectionError(Exception):
    """Raised when a warehouse entity cannot be safely deleted."""


class WarehouseCrudService:
    """Application-сервис CRUD-операций модераторского склада."""

    CATEGORY_ACTIVE_ORDER_MESSAGE = (
        "Категория не может быть удалена, так как её товары используются в активных заказах"
    )
    PRODUCT_ACTIVE_ORDER_MESSAGE = "Товар не может быть удалён, так как участвует в активных заказах"
    VARIANT_ACTIVE_RESERVE_MESSAGE = "Вариант товара не может быть удалён, так как по нему существуют активные резервы"

    @staticmethod
    def _reserve_relevant_orders(queryset):
        from orders.application.order_status_policy import OrderStatusPolicy

        return OrderStatusPolicy.reserve_relevant_queryset(queryset)

    @classmethod
    def category_has_active_orders(cls, category: Category) -> bool:
        return cls._reserve_relevant_orders(
            Order.objects.filter(items__product_variant__product__category=category)
        ).exists()

    @classmethod
    def product_has_active_orders(cls, product: Product) -> bool:
        return cls._reserve_relevant_orders(Order.objects.filter(items__product_variant__product=product)).exists()

    @classmethod
    def variant_has_active_reservations(cls, variant: ProductVariant) -> bool:
        if (variant.reserved_quantity or 0) <= 0:
            return False
        return cls._reserve_relevant_orders(Order.objects.filter(items__product_variant=variant)).exists()

    @classmethod
    def ensure_category_can_be_deleted(cls, category: Category) -> None:
        if cls.category_has_active_orders(category):
            raise WarehouseDeleteProtectionError(cls.CATEGORY_ACTIVE_ORDER_MESSAGE)

    @classmethod
    def ensure_product_can_be_deleted(cls, product: Product) -> None:
        if cls.product_has_active_orders(product):
            raise WarehouseDeleteProtectionError(cls.PRODUCT_ACTIVE_ORDER_MESSAGE)

    @classmethod
    def ensure_variant_can_be_deleted(cls, variant: ProductVariant) -> None:
        if cls.variant_has_active_reservations(variant):
            raise WarehouseDeleteProtectionError(cls.VARIANT_ACTIVE_RESERVE_MESSAGE)

    @classmethod
    def delete_category(cls, category: Category):
        with transaction.atomic():
            cls.ensure_category_can_be_deleted(category)
            return category.delete()

    @classmethod
    def delete_product(cls, product: Product):
        with transaction.atomic():
            cls.ensure_product_can_be_deleted(product)
            return product.delete()

    @classmethod
    def delete_variant(cls, variant: ProductVariant):
        with transaction.atomic():
            cls.ensure_variant_can_be_deleted(variant)
            return variant.delete()

    @staticmethod
    def save_product(form, is_on_sale=None):
        product = form.save(commit=False)
        if is_on_sale is not None:
            product.is_on_sale = bool(is_on_sale)
        product.save()
        form.save_m2m()
        return product

    @staticmethod
    def update_product(product, data):
        form = ProductForm(data, instance=product)
        if form.is_valid():
            form.save()
        return form

    @staticmethod
    def set_product_sale_state(product, is_on_sale: bool):
        product.is_on_sale = bool(is_on_sale)
        product.save(update_fields=["is_on_sale", "updated_at"])
        return product

    @staticmethod
    def save_variant(form, product=None):
        if product is not None:
            form.instance.product = product
        return form.save()

    @staticmethod
    def update_variant_stock(variant, data):
        form = VariantStockForm(data, instance=variant)
        if form.is_valid():
            form.save()
        return form

    @staticmethod
    def save_product_image(form, product):
        form.instance.product = product
        if form.cleaned_data.get("is_primary"):
            product.images.update(is_primary=False)
        return form.save()

    @staticmethod
    def set_primary_product_image(image):
        with transaction.atomic():
            image.product.images.exclude(pk=image.pk).filter(is_primary=True).update(is_primary=False)
            if not image.is_primary:
                image.is_primary = True
                image.save(update_fields=["is_primary"])
        return image
