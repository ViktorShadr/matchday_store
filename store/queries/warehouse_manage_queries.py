from store.forms import ProductForm, VariantStockForm
from store.models import Product


class WarehouseManagementQueryService:
    """Query-сервис для страницы управления товаром на складе."""

    @staticmethod
    def get_product_manage_queryset():
        return Product.objects.select_related("category").prefetch_related("images", "variants__image")

    @staticmethod
    def build_product_manage_context(product, product_form=None) -> dict:
        variants = list(product.variants.order_by("size", "color", "pk"))
        for variant in variants:
            variant.stock_form = VariantStockForm(instance=variant)

        return {
            "product_form": product_form or ProductForm(instance=product),
            "variants": variants,
            "images": product.images.order_by("-is_primary", "-created_at"),
        }
