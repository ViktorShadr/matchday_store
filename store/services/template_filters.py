"""
Сервис для подготовки данных для шаблонов.
Содержит функции для обогащения объектов необходимыми для отображения атрибутами.
"""

from typing import List, Dict, Any

from store.presenters import CartItemPresenter, CategoryPresenter, PermissionPresenter, ProductDetailsPresenter


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
        return PermissionPresenter.is_moderator(user)

    @staticmethod
    def is_staff(user) -> bool:
        """
        Проверить, является ли пользователь персоналом.

        Args:
            user: Объект пользователя

        Returns:
            bool: True если пользователь персонал, False иначе
        """
        return PermissionPresenter.is_staff(user)

    @staticmethod
    def get_user_permissions(user) -> Dict[str, bool]:
        """
        Получить все права пользователя для использования в контексте.

        Args:
            user: Объект пользователя

        Returns:
            Dict[str, bool]: Словарь с правами
        """
        return PermissionPresenter.present(user)


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
        return CategoryPresenter.present(category, user=user)

class ProductDisplayService:
    """Сервис для подготовки данных товаров к отображению в шаблонах"""

    @staticmethod
    def prepare_product_details(product) -> Dict[str, Any]:
        """
        Подготовить детальные данные товара для страницы товара.

        Args:
            product: Объект товара с обогащёнными данными

        Returns:
            Dict[str, Any]: Словарь с детальными данными
        """
        return ProductDetailsPresenter.present(product)

    @staticmethod
    def prepare_variant_data(variant) -> Dict[str, Any]:
        """
        Подготовить данные варианта товара.

        Args:
            variant: Объект варианта товара

        Returns:
            Dict[str, Any]: Словарь с данными варианта
        """
        return ProductDetailsPresenter.present_variant(variant)

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
        return CartItemPresenter.present(cart_item)

    @staticmethod
    def _clean_variant_value(value: Any) -> str:
        return CartItemPresenter.clean_variant_value(value)

    @staticmethod
    def prepare_cart_items(items) -> List[Dict[str, Any]]:
        """
        Подготовить список товаров в корзине для отображения.

        Args:
            items: Список CartItem объектов

        Returns:
            List[Dict[str, Any]]: Список обогащённых данных товаров
        """
        return CartItemPresenter.present_many(items)
