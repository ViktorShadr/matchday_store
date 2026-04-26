import logging
from typing import Optional
from django.db import transaction

from ..models import ProductVariant
from ..repositories import ICartRepository, IProductVariantRepository
from ..repositories import CartRepository, ProductVariantRepository
from ..application.cart_context import CartContext
from .cart_exceptions import (
    InsufficientStockError,
    ProductVariantNotFoundError,
    ProductNotOnSaleError,
    CartOperationError,
)

logger = logging.getLogger(__name__)


def _clean_variant_value(value) -> str:
    """Нормализовать значение варианта для отображения в UI."""
    if value is None:
        return ""
    normalized = str(value).strip()
    if normalized.lower() == "none":
        return ""
    return normalized


class CartService:
    """
    Сервис для работы с корзиной.

    Реализует best practices:
    - Использование @transaction.atomic для предотвращения race conditions
    - select_for_update() для блокировки записей в БД
    - Правильная обработка исключений
    - Логирование операций
    - Dependency Injection для репозиториев (DIP)
    """

    def __init__(
        self,
        cart_repository: Optional[ICartRepository] = None,
        product_variant_repository: Optional[IProductVariantRepository] = None,
    ):
        """
        Инициализация сервиса с возможностью DI.

        Args:
            cart_repository: Репозиторий корзины (по умолчанию CartRepository)
            product_variant_repository: Репозиторий вариантов товаров (по умолчанию ProductVariantRepository)
        """
        self.cart_repository = cart_repository or CartRepository()
        self.product_variant_repository = product_variant_repository or ProductVariantRepository()

    @transaction.atomic
    def add_item(self, cart_context: CartContext, product_variant_id, quantity=1):
        """
        Добавить товар в корзину с защитой от race conditions.

        Использует select_for_update() для блокировки варианта товара
        на время операции, что предотвращает race conditions.

        Args:
            request: HTTP запрос
            product_variant_id: ID варианта товара
            quantity: Количество товара для добавления

        Returns:
            CartItem: Добавленный или обновленный элемент корзины

        Raises:
            ProductVariantNotFoundError: Если вариант не найден
            InsufficientStockError: Если недостаточно товара на складе
            CartOperationError: При других ошибках операции
        """
        try:
            # Получаем вариант товара с блокировкой (select_for_update)
            # Это предотвращает race conditions при одновременных запросах
            product_variant = self.product_variant_repository.get_variant_for_update(product_variant_id)

            logger.info("User %s adding variant %s qty %s", cart_context.actor_label, product_variant_id, quantity)

            if not product_variant.product.is_on_sale:
                raise ProductNotOnSaleError("Товар снят с продажи и недоступен для заказа.")

            # Проверяем наличие товара
            if product_variant.quantity < quantity:
                logger.warning(
                    f"Insufficient stock: variant {product_variant_id}, "
                    f"available {product_variant.quantity}, requested {quantity}"
                )
                raise InsufficientStockError(
                    f"Недостаточно товара на складе. Доступно: {product_variant.quantity}",
                    available_quantity=product_variant.quantity,
                )

            cart_item, created = self.cart_repository.get_or_create_cart_item(
                cart_context.cart, product_variant, {"quantity": quantity}
            )

            if not created:
                # Товар уже в корзине, обновляем количество
                new_quantity = cart_item.quantity + quantity

                if product_variant.quantity < new_quantity:
                    logger.warning(
                        f"Insufficient stock for update: variant {product_variant_id}, "
                        f"available {product_variant.quantity}, requested {new_quantity}"
                    )
                    raise InsufficientStockError(
                        f"Недостаточно товара на складе. Доступно: {product_variant.quantity}",
                        available_quantity=product_variant.quantity,
                    )

                cart_item.quantity = new_quantity
                cart_item.save()
                logger.info(f"Cart item updated: {cart_item.id}, qty={new_quantity}")
            else:
                logger.info(f"New cart item created: {cart_item.id}, qty={quantity}")

            return cart_item

        except ProductVariant.DoesNotExist:
            logger.error(f"Product variant not found: {product_variant_id}")
            raise ProductVariantNotFoundError(f"Вариант товара с ID {product_variant_id} не найден")
        except (InsufficientStockError, ProductVariantNotFoundError, ProductNotOnSaleError):
            # Пробрасываем свои исключения дальше
            raise
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при добавлении товара в корзину: {str(e)}")

    @transaction.atomic
    def update_item_quantity(self, cart_context: CartContext, product_variant_id, quantity):
        """
        Обновить количество товара в корзине с защитой от race conditions.

        Args:
            request: HTTP запрос
            product_variant_id: ID варианта товара
            quantity: Новое количество

        Returns:
            CartItem: Обновленный элемент корзины

        Raises:
            ProductVariantNotFoundError: Если вариант не найден
            InsufficientStockError: Если недостаточно товара на складе
            CartOperationError: При других ошибках операции
        """
        try:
            # Получаем вариант товара с блокировкой
            product_variant = self.product_variant_repository.get_variant_for_update(product_variant_id)

            logger.info("User %s updating variant %s qty to %s", cart_context.actor_label, product_variant_id, quantity)

            if not product_variant.product.is_on_sale:
                raise ProductNotOnSaleError("Товар снят с продажи и недоступен для заказа.")

            if quantity < 1:
                raise ValueError("Количество должно быть больше 0")

            if product_variant.quantity < quantity:
                logger.warning(
                    f"Insufficient stock for update: variant {product_variant_id}, "
                    f"available {product_variant.quantity}, requested {quantity}"
                )
                raise InsufficientStockError(
                    f"Недостаточно товара на складе. Доступно: {product_variant.quantity}",
                    available_quantity=product_variant.quantity,
                )

            cart_item, created = self.cart_repository.update_or_create_cart_item(
                cart_context.cart, product_variant, {"quantity": quantity}
            )

            logger.info(f"Cart item {'created' if created else 'updated'}: {cart_item.id}, qty={quantity}")

            return cart_item

        except ProductVariant.DoesNotExist:
            logger.error(f"Product variant not found: {product_variant_id}")
            raise ProductVariantNotFoundError(f"Вариант товара с ID {product_variant_id} не найден")
        except (InsufficientStockError, ProductVariantNotFoundError, ProductNotOnSaleError, ValueError):
            raise
        except Exception as e:
            logger.error(f"Error updating cart item: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при обновлении товара в корзине: {str(e)}")

    @transaction.atomic
    def remove_item(self, cart_context: CartContext, product_variant_id):
        """
        Удалить товар из корзины.

        Args:
            request: HTTP запрос
            product_variant_id: ID варианта товара

        Returns:
            bool: True если товар удалён, False если товара не было в корзине
        """
        try:
            success = self.cart_repository.delete_cart_item(cart_context.cart, product_variant_id)
            if success:
                logger.info("Cart item removed: %s from user %s", product_variant_id, cart_context.actor_label)
            else:
                logger.warning("Cart item not found: %s in cart %s", product_variant_id, cart_context.cart.id)
            return success
        except Exception as e:
            logger.error(f"Error removing item from cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при удалении товара из корзины: {str(e)}")

    def get_cart_summary(self, cart_context: CartContext):
        """
        Получить сводку по корзине.

        Кэшируется на время одного запроса для избежания множественных
        вызовов get_or_create_cart.

        Returns:
            dict: Сводка с общей суммой, количеством товаров и списком элементов
        """
        items = self.cart_repository.get_cart_items(cart_context.cart)

        return {
            "total_items": cart_context.cart.total_items,
            "total_price": cart_context.cart.total_price,
            "items": items,
        }

    def get_cart_items_with_details(self, cart):
        """
        Получить товары корзины с детальной информацией для отображения.

        Args:
            cart: Объект корзины

        Returns:
            list: Список словарей с информацией о товарах
        """
        items = []
        for item in cart.items.select_related(
            'product_variant',
            'product_variant__product'
        ).prefetch_related('product_variant__product__images').all():
            variant = item.product_variant
            product = variant.product
            size = _clean_variant_value(variant.size)
            color = _clean_variant_value(variant.color)
            variant_parts = [part for part in (size, color) if part]
            variant_label = " / ".join(variant_parts)

            # Get product image
            image_url = None
            product_images = list(product.images.all())
            primary_image = next((img for img in product_images if img.is_primary), None)
            first_image = primary_image or (product_images[0] if product_images else None)
            if first_image:
                image_url = first_image.image.url if first_image.image else None

            items.append({
                'variant_id': variant.id,
                'product_id': product.id,
                'product_name': product.name,
                'size': size or None,
                'color': color or None,
                'variant_label': variant_label,
                'quantity': item.quantity,
                'price': variant.price,
                'total_price': item.total_price,
                'total_price_formatted': f"{item.total_price:,}".replace(",", " "),
                'image': image_url,
                'max_quantity': variant.quantity,
            })
        return items
