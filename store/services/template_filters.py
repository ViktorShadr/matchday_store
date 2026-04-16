"""
Сервис для подготовки данных для шаблонов.
Содержит функции для обогащения объектов необходимыми для отображения атрибутами.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from store.mixins import is_moderator_user


class PermissionService:
    """Сервис для проверки прав доступа в шаблонах"""

    @staticmethod
    def is_moderator(user) -> bool:
        """
        Проверить, является ли пользователь модератором.

        Args:
            user: Объект пользователя

        Returns:
            bool: True если пользователь модератор, False иначе
        """
        return is_moderator_user(user)

    @staticmethod
    def is_staff(user) -> bool:
        """
        Проверить, является ли пользователь персоналом.

        Args:
            user: Объект пользователя

        Returns:
            bool: True если пользователь персонал, False иначе
        """
        return user.is_authenticated and user.is_staff

    @staticmethod
    def get_user_permissions(user) -> Dict[str, bool]:
        """
        Получить все права пользователя для использования в контексте.

        Args:
            user: Объект пользователя

        Returns:
            Dict[str, bool]: Словарь с правами
        """
        return {
            "is_moderator": PermissionService.is_moderator(user),
            "is_staff": PermissionService.is_staff(user),
            "is_authenticated": user.is_authenticated,
        }


class CategoryService:
    """Сервис для работы с категориями в шаблонах"""

    @staticmethod
    def enrich_category(category, user=None) -> Dict[str, Any]:
        """
        Обогатить объект категории данными для отображения.

        Args:
            category: Объект категории
            user: Объект пользователя для проверки прав (опционально)

        Returns:
            Dict[str, Any]: Словарь с обогащёнными данными
        """
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
            data["user_permissions"] = PermissionService.get_user_permissions(user)

        return data

    @staticmethod
    def enrich_categories(categories, user=None) -> List[Dict[str, Any]]:
        """
        Обогатить список категорий данными для отображения.

        Args:
            categories: Список или queryset категорий
            user: Объект пользователя для проверки прав (опционально)

        Returns:
            List[Dict[str, Any]]: Список обогащённых категорий
        """
        return [CategoryService.enrich_category(cat, user) for cat in categories]


class ProductDisplayService:
    """Сервис для подготовки данных товаров к отображению в шаблонах"""

    @staticmethod
    def prepare_product_card_data(product) -> Dict[str, Any]:
        """
        Подготовить данные товара для карточки товара.

        Используется в шаблоне _product_card.html для отображения товара.

        Args:
            product: Объект товара (должен быть обогащён через catalog_service.enrich_product)

        Returns:
            Dict[str, Any]: Словарь с данными для отображения
        """
        return {
            "id": product.pk,
            "name": product.name,
            "title": getattr(product, "title", None) or product.name,
            "price": getattr(product, "display_price", None),
            "image": getattr(product, "display_image", None),
            "url": product.get_absolute_url(),
            "price_formatted": (
                f"{getattr(product, 'display_price', '—')} ₽" if getattr(product, "display_price", None) else "—"
            ),
        }

    @staticmethod
    def prepare_product_details(product) -> Dict[str, Any]:
        """
        Подготовить детальные данные товара для страницы товара.

        Args:
            product: Объект товара с обогащёнными данными

        Returns:
            Dict[str, Any]: Словарь с детальными данными
        """
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
            "variants": [ProductDisplayService.prepare_variant_data(v) for v in variants],
            "variants_exist": len(variants) > 0,
            "images_exist": len(images) > 0,
        }

    @staticmethod
    def prepare_variant_data(variant) -> Dict[str, Any]:
        """
        Подготовить данные варианта товара.

        Args:
            variant: Объект варианта товара

        Returns:
            Dict[str, Any]: Словарь с данными варианта
        """
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

    @staticmethod
    def prepare_category_product(product) -> Dict[str, Any]:
        """
        Подготовить данные товара для списка в категории.

        Args:
            product: Объект товара

        Returns:
            Dict[str, Any]: Словарь с данными товара для категории
        """
        return {
            "id": product.pk,
            "name": product.name,
            "description": (
                product.description[:200] + "..."
                if product.description and len(product.description) > 200
                else product.description
            ),
            "created_at": product.created_at,
            "created_at_formatted": product.created_at.strftime("%d.%m.%Y") if product.created_at else "",
            "url": product.get_absolute_url(),
        }


class CartDisplayService:
    """Сервис для подготовки данных корзины к отображению"""

    @staticmethod
    def prepare_cart_item(cart_item) -> Dict[str, Any]:
        """
        Подготовить данные товара в корзине для отображения.

        Args:
            cart_item: Объект CartItem

        Returns:
            Dict[str, Any]: Словарь с данными товара в корзине
        """
        variant = cart_item.product_variant
        product = variant.product
        size = CartDisplayService._clean_variant_value(variant.size)
        color = CartDisplayService._clean_variant_value(variant.color)
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
            "max_quantity": variant.quantity,
            "total_price": cart_item.total_price,
            "total_price_formatted": f"{cart_item.total_price} ₽",
            "image": getattr(variant.image.image if variant.image else None, "url", None),
        }

    @staticmethod
    def _clean_variant_value(value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).strip()
        if normalized.lower() == "none":
            return ""
        return normalized

    @staticmethod
    def prepare_cart_items(items) -> List[Dict[str, Any]]:
        """
        Подготовить список товаров в корзине для отображения.

        Args:
            items: Список CartItem объектов

        Returns:
            List[Dict[str, Any]]: Список обогащённых данных товаров
        """
        return [CartDisplayService.prepare_cart_item(item) for item in items]


class DateService:
    """Сервис для форматирования дат в шаблонах"""

    @staticmethod
    def format_datetime(dt: Optional[datetime], format_str: str = "%d.%m.%Y %H:%M") -> str:
        """
        Форматировать datetime объект в строку.

        Args:
            dt: Datetime объект
            format_str: Строка формата

        Returns:
            str: Отформатированная строка даты
        """
        if not dt:
            return ""
        return dt.strftime(format_str)

    @staticmethod
    def format_date(dt: Optional[datetime], format_str: str = "%d.%m.%Y") -> str:
        """
        Форматировать datetime объект в строку только с датой.

        Args:
            dt: Datetime объект
            format_str: Строка формата

        Returns:
            str: Отформатированная строка даты
        """
        return DateService.format_datetime(dt, format_str)
