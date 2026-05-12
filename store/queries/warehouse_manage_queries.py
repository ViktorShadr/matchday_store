from store.forms import ProductForm, VariantStockForm
from store.models import Product
from store.queries.dashboard_queries import WarehouseReservationQueryService


class WarehouseManagementQueryService:
    """Query-сервис для страницы управления товаром на складе."""

    @staticmethod
    def get_product_manage_queryset():
        return Product.objects.select_related("category").prefetch_related("images", "variants__image")

    @staticmethod
    def build_product_manage_context(product, product_form=None) -> dict:
        variants = list(product.variants.order_by("size", "color", "pk"))
        active_reservation_items_by_variant = WarehouseReservationQueryService.get_active_reservation_items_by_variant(
            variants
        )
        for variant in variants:
            variant.stock_form = VariantStockForm(instance=variant)
            variant.active_reservation_items = active_reservation_items_by_variant.get(variant.pk, [])

        return {
            "product_form": product_form or ProductForm(instance=product),
            "variants": variants,
            "images": product.images.order_by("-is_primary", "-created_at"),
        }
