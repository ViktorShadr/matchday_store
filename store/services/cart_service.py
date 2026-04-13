import logging
from django.db import transaction
from typing import Optional

from ..models import Cart, CartItem, ProductVariant
from ..repositories import ICartRepository, IProductVariantRepository
from ..repositories import CartRepository, ProductVariantRepository
from .cart_exceptions import (
    InsufficientStockError,
    ProductVariantNotFoundError,
    CartOperationError,
)
from .cart_validator import CartValidator

logger = logging.getLogger(__name__)


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

    def get_or_create_cart(self, request):
        """
        Получить или создать корзину для пользователя или сессии.

        Если пользователь авторизуется с активной сессионной корзиной,
        автоматически объединяет товары из обеих корзин.

        Args:
            request: HTTP запрос

        Returns:
            Cart: Объект корзины
        """
        if request.user.is_authenticated:
            cart = self.cart_repository.get_or_create_cart_by_user(request.user)
            # Если пользователь авторизовался и у него была корзина по сессии,
            # переносим товары в корзину пользователя
            if request.session.session_key:
                self._merge_session_cart_with_user_cart(cart, request.session.session_key)
        else:
            # Для анонимных пользователей используем сессию
            if not request.session.session_key:
                request.session.create()
                request.session.modified = True

            session_key = request.session.session_key
            cart = self.cart_repository.get_or_create_cart_by_session(session_key)

        return cart

    @transaction.atomic
    def _merge_session_cart_with_user_cart(self, user_cart, session_key):
        """
        Объединить сессионную корзину с корзиной пользователя.

        Выполняется в транзакции для обеспечения целостности данных.

        Args:
            user_cart: Корзина пользователя
            session_key: Ключ сессии для поиска сессионной корзины
        """
        try:
            session_cart = self.cart_repository.get_cart_by_session_key(session_key)
            if not session_cart:
                return

            # Переносим товары из сессионной корзины
            for item in session_cart.items.select_related("product_variant").all():
                available_quantity = item.product_variant.quantity
                if available_quantity < 1:
                    continue

                cart_item, created = self.cart_repository.get_or_create_cart_item(
                    user_cart, item.product_variant, {"quantity": item.quantity}
                )

                if created and cart_item.quantity > available_quantity:
                    cart_item.quantity = available_quantity
                    cart_item.save()
                elif not created:
                    new_quantity = min(cart_item.quantity + item.quantity, available_quantity)
                    if cart_item.quantity != new_quantity:
                        cart_item.quantity = new_quantity
                        cart_item.save()
                    logger.info(
                        f"Merged cart item: user={user_cart.user.id}, "
                        f"variant={item.product_variant.id}, qty={cart_item.quantity}"
                    )

            # Удаляем сессионную корзину
            self.cart_repository.delete_cart(session_cart)
            logger.info(f"Session cart {session_key[:8]}... merged and deleted")

        except Exception as e:
            logger.error(f"Error merging carts: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при объединении корзин: {str(e)}")

    @transaction.atomic
    def add_item(self, request, product_variant_id, quantity=1):
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

            logger.info(
                f"User {request.user.id if request.user.is_authenticated else 'anonymous'} "
                f"adding variant {product_variant_id} qty {quantity}"
            )

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

            cart = self.get_or_create_cart(request)

            cart_item, created = self.cart_repository.get_or_create_cart_item(
                cart, product_variant, {"quantity": quantity}
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
        except (InsufficientStockError, ProductVariantNotFoundError):
            # Пробрасываем свои исключения дальше
            raise
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при добавлении товара в корзину: {str(e)}")

    @transaction.atomic
    def update_item_quantity(self, request, product_variant_id, quantity):
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

            logger.info(
                f"User {request.user.id if request.user.is_authenticated else 'anonymous'} "
                f"updating variant {product_variant_id} qty to {quantity}"
            )

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

            cart = self.get_or_create_cart(request)

            cart_item, created = self.cart_repository.update_or_create_cart_item(
                cart, product_variant, {"quantity": quantity}
            )

            logger.info(f"Cart item {'created' if created else 'updated'}: {cart_item.id}, qty={quantity}")

            return cart_item

        except ProductVariant.DoesNotExist:
            logger.error(f"Product variant not found: {product_variant_id}")
            raise ProductVariantNotFoundError(f"Вариант товара с ID {product_variant_id} не найден")
        except (InsufficientStockError, ProductVariantNotFoundError, ValueError) as e:
            raise
        except Exception as e:
            logger.error(f"Error updating cart item: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при обновлении товара в корзине: {str(e)}")

    @transaction.atomic
    def remove_item(self, request, product_variant_id):
        """
        Удалить товар из корзины.

        Args:
            request: HTTP запрос
            product_variant_id: ID варианта товара

        Returns:
            bool: True если товар удалён, False если товара не было в корзине
        """
        try:
            cart = self.get_or_create_cart(request)

            success = self.cart_repository.delete_cart_item(cart, product_variant_id)
            if success:
                logger.info(
                    f"Cart item removed: {product_variant_id} from user "
                    f"{request.user.id if request.user.is_authenticated else 'anonymous'}"
                )
            else:
                logger.warning(f"Cart item not found: {product_variant_id} in cart {cart.id}")
            return success
        except Exception as e:
            logger.error(f"Error removing item from cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при удалении товара из корзины: {str(e)}")

    @transaction.atomic
    def clear_cart(self, request):
        """
        Очистить корзину.

        Args:
            request: HTTP запрос

        Returns:
            Cart: Объект корзины
        """
        try:
            cart = self.get_or_create_cart(request)
            items_count = self.cart_repository.delete_cart_items(cart)
            logger.info(
                f"Cart cleared: removed {items_count} items from user "
                f"{request.user.id if request.user.is_authenticated else 'anonymous'}"
            )
            return cart
        except Exception as e:
            logger.error(f"Error clearing cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при очистке корзины: {str(e)}")

    def get_cart_items(self, request):
        """
        Получить все товары из корзины.

        Args:
            request: HTTP запрос

        Returns:
            QuerySet: Список элементов корзины
        """
        cart = self.get_or_create_cart(request)
        return self.cart_repository.get_cart_items(cart)

    def get_cart_summary(self, request):
        """
        Получить сводку по корзине.

        Кэшируется на время одного запроса для избежания множественных
        вызовов get_or_create_cart.

        Args:
            request: HTTP запрос

        Returns:
            dict: Сводка с общей суммой, количеством товаров и списком элементов
        """
        cart = self.get_or_create_cart(request)
        items = self.cart_repository.get_cart_items(cart)

        return {"total_items": cart.total_items, "total_price": cart.total_price, "items": items}

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

            # Get product image
            image_url = None
            product_images = list(product.images.all())
            primary_image = next((img for img in product_images if img.is_primary), None)
            first_image = primary_image or (product_images[0] if product_images else None)
            if first_image:
                image_url = first_image.image.url if first_image.image else None

            items.append({
                'variant_id': variant.id,
                'product_name': product.name,
                'size': variant.size,
                'color': variant.color,
                'quantity': item.quantity,
                'price': variant.price,
                'total_price': item.total_price,
                'total_price_formatted': f"{item.total_price:,}".replace(",", " "),
                'image': image_url,
                'max_quantity': variant.quantity,
            })
        return items

    @transaction.atomic
    def merge_carts_on_login(self, user, session_key):
        """
        Объединить корзины при авторизации пользователя.

        Вызывается из сигналов при авторизации пользователя.

        Args:
            user: Объект пользователя
            session_key: Ключ сессии
        """
        if not session_key:
            return

        try:
            session_cart = self.cart_repository.get_cart_by_session_key(session_key)
            if not session_cart:
                return

            user_cart = self.cart_repository.get_or_create_cart_by_user(user)

            # Переносим товары из сессионной корзины в корзину пользователя
            for item in session_cart.items.select_related("product_variant").all():
                available_quantity = item.product_variant.quantity
                if available_quantity < 1:
                    continue

                cart_item, created = self.cart_repository.get_or_create_cart_item(
                    user_cart, item.product_variant, {"quantity": item.quantity}
                )
                if created and cart_item.quantity > available_quantity:
                    cart_item.quantity = available_quantity
                    cart_item.save()
                elif not created:
                    new_quantity = min(cart_item.quantity + item.quantity, available_quantity)
                    if cart_item.quantity != new_quantity:
                        cart_item.quantity = new_quantity
                        cart_item.save()

            # Удаляем сессионную корзину
            self.cart_repository.delete_cart(session_cart)
            logger.info(f"Session cart {session_key[:8]}... merged on login for user {user.id}")

        except Exception as e:
            logger.error(f"Error merging carts on login: {e}", exc_info=True)
