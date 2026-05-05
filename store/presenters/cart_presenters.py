from typing import Any


class CartItemPresenter:
    """Подготовка cart item к отображению."""

    @staticmethod
    def clean_variant_value(value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).strip()
        if normalized.lower() == "none":
            return ""
        return normalized

    @classmethod
    def present(cls, cart_item):
        variant = cart_item.product_variant
        product = variant.product
        size = cls.clean_variant_value(variant.size)
        color = cls.clean_variant_value(variant.color)
        variant_parts = [part for part in (size, color) if part]

        return {
            "variant_id": variant.id,
            "product_id": product.id,
            "product_name": product.name,
            "size": size or None,
            "color": color or None,
            "variant_label": " / ".join(variant_parts),
            "price": variant.price,
            "price_formatted": f"{variant.price} ₽",
            "quantity": cart_item.quantity,
            "max_quantity": variant.available_quantity,
            "total_price": cart_item.total_price,
            "total_price_formatted": f"{cart_item.total_price} ₽",
            "image": getattr(variant.image.image if variant.image else None, "url", None),
        }

    @classmethod
    def present_many(cls, items):
        return [cls.present(item) for item in items]
