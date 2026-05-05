"""
Валидаторы для операций с корзиной.
"""

import logging
from typing import Tuple

from .cart_exceptions import InvalidQuantityError, ProductVariantNotFoundError

logger = logging.getLogger(__name__)


class CartValidator:
    """Валидатор данных для операций с корзиной"""

    MIN_QUANTITY = 1
    MAX_QUANTITY = 999

    @staticmethod
    def validate_variant_id(variant_id) -> int:
        """
        Валидировать ID варианта товара.

        Args:
            variant_id: ID варианта из запроса

        Returns:
            int: Валидированный ID

        Raises:
            ProductVariantNotFoundError: Если ID не валиден
        """
        if not variant_id:
            raise ProductVariantNotFoundError("ID варианта товара не указан")

        try:
            variant_id = int(variant_id)
            if variant_id <= 0:
                raise ValueError()
            return variant_id
        except (ValueError, TypeError):
            raise ProductVariantNotFoundError("ID варианта товара должен быть положительным числом")

    @staticmethod
    def validate_quantity(quantity_str) -> int:
        """
        Валидировать количество товара.

        Args:
            quantity_str: Количество из запроса (может быть строкой)

        Returns:
            int: Валидированное количество

        Raises:
            InvalidQuantityError: Если количество некорректно
        """
        try:
            quantity = int(quantity_str) if quantity_str else CartValidator.MIN_QUANTITY

            if quantity < CartValidator.MIN_QUANTITY:
                raise ValueError(f"Минимальное количество: {CartValidator.MIN_QUANTITY}")

            if quantity > CartValidator.MAX_QUANTITY:
                raise ValueError(f"Максимальное количество: {CartValidator.MAX_QUANTITY}")

            return quantity
        except (ValueError, TypeError):
            raise InvalidQuantityError(
                f"Количество должно быть числом от {CartValidator.MIN_QUANTITY} до {CartValidator.MAX_QUANTITY}"
            )

    @staticmethod
    def validate_add_to_cart_input(variant_id, quantity_str) -> Tuple[int, int]:
        """
        Валидировать входные данные для добавления товара в корзину.

        Args:
            variant_id: ID варианта
            quantity_str: Количество

        Returns:
            Tuple[int, int]: Кортеж (variant_id, quantity)

        Raises:
            ProductVariantNotFoundError | InvalidQuantityError
        """
        variant_id = CartValidator.validate_variant_id(variant_id)
        quantity = CartValidator.validate_quantity(quantity_str)
        return variant_id, quantity

    @staticmethod
    def validate_update_quantity_input(variant_id, quantity_str) -> Tuple[int, int]:
        """
        Валидировать входные данные для обновления количества товара.

        Args:
            variant_id: ID варианта
            quantity_str: Количество

        Returns:
            Tuple[int, int]: Кортеж (variant_id, quantity)

        Raises:
            ProductVariantNotFoundError | InvalidQuantityError
        """
        # Используем те же правила что и для добавления
        return CartValidator.validate_add_to_cart_input(variant_id, quantity_str)

    @staticmethod
    def validate_remove_item_input(variant_id) -> int:
        """
        Валидировать входные данные для удаления товара.

        Args:
            variant_id: ID варианта

        Returns:
            int: Валидированный ID

        Raises:
            ProductVariantNotFoundError
        """
        return CartValidator.validate_variant_id(variant_id)
