import logging
from django.db import transaction
from ..models import Cart, CartItem, ProductVariant
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
    """
    
    @staticmethod
    def get_or_create_cart(request):
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
            cart, created = Cart.objects.get_or_create(
                user=request.user,
                defaults={'session_key': None}
            )
            # Если пользователь авторизовался и у него была корзина по сессии,
            # переносим товары в корзину пользователя
            if not created and request.session.session_key:
                CartService._merge_session_cart_with_user_cart(cart, request.session.session_key)
        else:
            # Для анонимных пользователей используем сессию
            if not request.session.session_key:
                request.session.create()
                request.session.modified = True
            
            session_key = request.session.session_key
            cart, created = Cart.objects.get_or_create(
                session_key=session_key,
                user__isnull=True,
                defaults={'session_key': session_key}
            )
        
        return cart
    
    @staticmethod
    @transaction.atomic
    def _merge_session_cart_with_user_cart(user_cart, session_key):
        """
        Объединить сессионную корзину с корзиной пользователя.
        
        Выполняется в транзакции для обеспечения целостности данных.
        
        Args:
            user_cart: Корзина пользователя
            session_key: Ключ сессии для поиска сессионной корзины
        """
        try:
            session_cart = Cart.objects.get(
                session_key=session_key,
                user__isnull=True
            )
            
            # Переносим товары из сессионной корзины
            for item in session_cart.items.all():
                cart_item, created = CartItem.objects.get_or_create(
                    cart=user_cart,
                    product_variant=item.product_variant,
                    defaults={'quantity': item.quantity}
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save()
                    logger.info(
                        f"Merged cart item: user={user_cart.user.id}, "
                        f"variant={item.product_variant.id}, qty={cart_item.quantity}"
                    )
            
            # Удаляем сессионную корзину
            session_cart.delete()
            logger.info(f"Session cart {session_key[:8]}... merged and deleted")
            
        except Cart.DoesNotExist:
            # Сессионной корзины нет, это нормально
            pass
        except Exception as e:
            logger.error(f"Error merging carts: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при объединении корзин: {str(e)}")
    
    @staticmethod
    @transaction.atomic
    def add_item(request, product_variant_id, quantity=1):
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
            product_variant = ProductVariant.objects.select_for_update().get(
                id=product_variant_id
            )
            
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
                    available_quantity=product_variant.quantity
                )
            
            cart = CartService.get_or_create_cart(request)
            
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product_variant=product_variant,
                defaults={'quantity': quantity}
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
                        available_quantity=product_variant.quantity
                    )
                
                cart_item.quantity = new_quantity
                cart_item.save()
                logger.info(
                    f"Cart item updated: {cart_item.id}, qty={new_quantity}"
                )
            else:
                logger.info(
                    f"New cart item created: {cart_item.id}, qty={quantity}"
                )
            
            return cart_item
            
        except ProductVariant.DoesNotExist:
            logger.error(f"Product variant not found: {product_variant_id}")
            raise ProductVariantNotFoundError(
                f"Вариант товара с ID {product_variant_id} не найден"
            )
        except (InsufficientStockError, ProductVariantNotFoundError):
            # Пробрасываем свои исключения дальше
            raise
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при добавлении товара в корзину: {str(e)}")
    
    @staticmethod
    @transaction.atomic
    def update_item_quantity(request, product_variant_id, quantity):
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
            product_variant = ProductVariant.objects.select_for_update().get(
                id=product_variant_id
            )
            
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
                    available_quantity=product_variant.quantity
                )
            
            cart = CartService.get_or_create_cart(request)
            
            cart_item, created = CartItem.objects.update_or_create(
                cart=cart,
                product_variant=product_variant,
                defaults={'quantity': quantity}
            )
            
            logger.info(
                f"Cart item {'created' if created else 'updated'}: {cart_item.id}, qty={quantity}"
            )
            
            return cart_item
            
        except ProductVariant.DoesNotExist:
            logger.error(f"Product variant not found: {product_variant_id}")
            raise ProductVariantNotFoundError(
                f"Вариант товара с ID {product_variant_id} не найден"
            )
        except (InsufficientStockError, ProductVariantNotFoundError, ValueError) as e:
            raise
        except Exception as e:
            logger.error(f"Error updating cart item: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при обновлении товара в корзине: {str(e)}")
    
    @staticmethod
    @transaction.atomic
    def remove_item(request, product_variant_id):
        """
        Удалить товар из корзины.
        
        Args:
            request: HTTP запрос
            product_variant_id: ID варианта товара
            
        Returns:
            bool: True если товар удалён, False если товара не было в корзине
        """
        try:
            cart = CartService.get_or_create_cart(request)
            
            try:
                cart_item = CartItem.objects.get(
                    cart=cart,
                    product_variant_id=product_variant_id
                )
                cart_item.delete()
                logger.info(
                    f"Cart item removed: {product_variant_id} from user "
                    f"{request.user.id if request.user.is_authenticated else 'anonymous'}"
                )
                return True
            except CartItem.DoesNotExist:
                logger.warning(
                    f"Cart item not found: {product_variant_id} in cart {cart.id}"
                )
                return False
        except Exception as e:
            logger.error(f"Error removing item from cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при удалении товара из корзины: {str(e)}")
    
    @staticmethod
    @transaction.atomic
    def clear_cart(request):
        """
        Очистить корзину.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Cart: Объект корзины
        """
        try:
            cart = CartService.get_or_create_cart(request)
            items_count = cart.items.count()
            cart.items.all().delete()
            logger.info(
                f"Cart cleared: removed {items_count} items from user "
                f"{request.user.id if request.user.is_authenticated else 'anonymous'}"
            )
            return cart
        except Exception as e:
            logger.error(f"Error clearing cart: {e}", exc_info=True)
            raise CartOperationError(f"Ошибка при очистке корзины: {str(e)}")
    
    @staticmethod
    def get_cart_items(request):
        """
        Получить все товары из корзины.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Список элементов корзины
        """
        cart = CartService.get_or_create_cart(request)
        return cart.items.select_related('product_variant__product').all()
    
    @staticmethod
    def get_cart_summary(request):
        """
        Получить сводку по корзине.
        
        Кэшируется на время одного запроса для избежания множественных
        вызовов get_or_create_cart.
        
        Args:
            request: HTTP запрос
            
        Returns:
            dict: Сводка с общей суммой, количеством товаров и списком элементов
        """
        cart = CartService.get_or_create_cart(request)
        items = cart.items.select_related('product_variant__product').all()
        
        return {
            'total_items': cart.total_items,
            'total_price': cart.total_price,
            'items': items
        }
    
    @staticmethod
    @transaction.atomic
    def merge_carts_on_login(user, session_key):
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
            session_cart = Cart.objects.get(
                session_key=session_key,
                user__isnull=True
            )
            
            user_cart, created = Cart.objects.get_or_create(
                user=user,
                defaults={'session_key': None}
            )
            
            # Переносим товары из сессионной корзины в корзину пользователя
            for item in session_cart.items.all():
                cart_item, created = CartItem.objects.get_or_create(
                    cart=user_cart,
                    product_variant=item.product_variant,
                    defaults={'quantity': item.quantity}
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save()
            
            # Удаляем сессионную корзину
            session_cart.delete()
            logger.info(f"Session cart {session_key[:8]}... merged on login for user {user.id}")
            
        except Cart.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error merging carts on login: {e}", exc_info=True)
