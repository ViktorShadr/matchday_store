from typing import Any

MODERATOR_GROUP_NAMES = ("Модераторы", "moderators")


class PermissionPresenter:
    """Презентация прав пользователя для шаблонов."""

    @staticmethod
    def is_moderator(user) -> bool:
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        return user.groups.filter(name__in=MODERATOR_GROUP_NAMES).exists()

    @staticmethod
    def is_staff(user) -> bool:
        return user.is_authenticated and user.is_staff

    @classmethod
    def present(cls, user) -> dict[str, bool]:
        return {
            "is_moderator": cls.is_moderator(user),
            "is_staff": cls.is_staff(user),
            "is_authenticated": user.is_authenticated,
        }


class CategoryPresenter:
    """Подготовка category к отображению."""

    @staticmethod
    def present(category, user=None) -> dict[str, Any]:
        data = {
            "category": category,
            "name": category.name,
            "description": category.description,
            "product_count": category.products.count(),
            "products_exist": category.products.exists(),
            "created_at": category.created_at,
            "updated_at": category.updated_at,
        }
        if user:
            data["user_permissions"] = PermissionPresenter.present(user)
        return data


class ProductCardPresenter:
    """Подготовка продукта к списковому отображению."""

    @staticmethod
    def enrich(product):
        images = sorted(list(product.images.all()), key=lambda image: (not image.is_primary, -image.id))
        variants = list(product.variants.all())
        available_variants = [variant for variant in variants if variant.quantity > 0]

        first_image = images[0] if images else None
        first_variant = variants[0] if variants else None

        product.gallery_images = images
        product.display_image = (
            first_image.image if first_image else getattr(getattr(first_variant, "image", None), "image", None)
        )
        price_source = available_variants if available_variants else variants
        if price_source:
            prices = [variant.price for variant in price_source if variant.price is not None]
            product.display_price = min(prices) if prices else None
        else:
            product.display_price = None

        product.in_stock = bool(available_variants)
        product.available_variant_count = len(available_variants)
        first_available_variant = available_variants[0] if available_variants else None
        product.first_available_variant_id = first_available_variant.id if first_available_variant else None
        return product

    @classmethod
    def enrich_many(cls, products):
        return [cls.enrich(product) for product in products]


class ProductDetailsPresenter:
    """Подготовка детальных данных товара."""

    @staticmethod
    def present(product) -> dict[str, Any]:
        variants = list(product.variants.all()) if hasattr(product, "variants") else []
        images = list(product.images.all()) if hasattr(product, "images") else []
        return {
            "id": product.pk,
            "name": product.name,
            "category": product.category.name if product.category else "Без категории",
            "description": product.description or "Описание пока не добавлено.",
            "price": getattr(product, "display_price", None),
            "image": getattr(product, "display_image", None),
            "images": images,
            "variants": [ProductDetailsPresenter.present_variant(v) for v in variants],
            "variants_exist": len(variants) > 0,
            "images_exist": len(images) > 0,
        }

    @staticmethod
    def present_variant(variant) -> dict[str, Any]:
        return {
            "id": variant.id,
            "size": variant.size,
            "color": variant.color,
            "price": variant.price,
            "price_formatted": f"{variant.price} ₽",
            "quantity": variant.quantity,
            "in_stock": variant.quantity > 0,
            "product_name": variant.product.name if variant.product else "",
        }
