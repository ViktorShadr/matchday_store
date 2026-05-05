"""
Исключения для операций с корзиной.
"""


class CartException(Exception):
    """Базовое исключение для операций с корзиной"""

    pass


class InsufficientStockError(CartException):
    """Недостаточно товара на складе"""

    http_status = 400

    def __init__(self, message: str, available_quantity: int = 0):
        """Инициализирует экземпляр класса."""
        self.message = message
        self.available_quantity = available_quantity
        super().__init__(message)


class InvalidQuantityError(CartException):
    """Некорректное количество товара"""

    http_status = 400


class ProductVariantNotFoundError(CartException):
    """Вариант товара не найден"""

    http_status = 404


class ProductNotOnSaleError(CartException):
    """Товар снят с продажи"""

    http_status = 400


class CartOperationError(CartException):
    """Ошибка при операции с корзиной"""

    http_status = 500
