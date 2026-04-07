import logging
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

from store.services.cart_service import CartService
from store.services.cart_validator import CartValidator
from store.services.cart_exceptions import (
    CartException,
    ProductVariantNotFoundError,
    InvalidQuantityError,
    InsufficientStockError,
    CartOperationError,
)

logger = logging.getLogger(__name__)


def build_error_response(exception: CartException) -> JsonResponse:
    """
    Построить JSON ответ с ошибкой на основе исключения.

    Args:
        exception: Исключение CartException

    Returns:
        JsonResponse: JSON ответ с кодом ошибки
    """
    status_code = getattr(exception, "http_status", 500)
    return JsonResponse(
        {"success": False, "error": str(exception.message if hasattr(exception, "message") else str(exception))},
        status=status_code,
    )


class AddToCartView(View):
    """
    Добавление товара в корзину.

    Обрабатывает AJAX-запросы на добавление товара в корзину.

    Требует:
    - CSRF token в заголовке X-CSRFToken или в теле запроса
    - variant_id: ID варианта товара
    - quantity: Количество (опционально, по умолчанию 1)

    Возвращает JSON:
    {
        "success": true|false,
        "message": "...",
        "cart_total": количество товаров в корзине
    }
    """

    @method_decorator(require_http_methods(["POST"]))
    def dispatch(self, *args, **kwargs):
        """Обрабатывает входящий HTTP-запрос и выбирает нужный метод."""
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Обрабатывает POST-запрос."""
        try:
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            quantity_str = request.POST.get("quantity", "1")

            variant_id, quantity = CartValidator.validate_add_to_cart_input(variant_id, quantity_str)

            # Добавляем товар в корзину
            cart_item = CartService.add_item(request, variant_id, quantity)
            cart = CartService.get_or_create_cart(request)

            return JsonResponse(
                {
                    "success": True,
                    "message": f'Товар "{cart_item.product_variant.product.name}" добавлен в корзину',
                    "cart_total": cart.total_items,
                }
            )

        except (ProductVariantNotFoundError, InvalidQuantityError, InsufficientStockError) as e:
            logger.warning(f"Validation error in add_to_cart: {e}")
            return build_error_response(e)
        except CartOperationError as e:
            logger.error(f"Operation error in add_to_cart: {e}")
            return build_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error in add_to_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при добавлении товара")
            return build_error_response(error)


class UpdateCartView(View):
    """
    Обновление количества товара в корзине.

    Требует:
    - CSRF token в заголовке X-CSRFToken или в теле запроса
    - variant_id: ID варианта товара
    - quantity: Новое количество

    Возвращает JSON:
    {
        "success": true|false,
        "message": "...",
        "item_total": сумма для одного товара,
        "cart_total": общая сумма корзины,
        "cart_items": количество товаров в корзине
    }
    """

    @method_decorator(require_http_methods(["POST"]))
    def dispatch(self, *args, **kwargs):
        """Обрабатывает входящий HTTP-запрос и выбирает нужный метод."""
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Обрабатывает POST-запрос."""
        try:
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            quantity_str = request.POST.get("quantity", "1")

            variant_id, quantity = CartValidator.validate_update_quantity_input(variant_id, quantity_str)

            # Обновляем товар в корзине
            cart_item = CartService.update_item_quantity(request, variant_id, quantity)
            cart = CartService.get_or_create_cart(request)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Количество товара обновлено",
                    "item_total": float(cart_item.total_price),
                    "cart_total": float(cart.total_price),
                    "cart_items": cart.total_items,
                }
            )

        except (ProductVariantNotFoundError, InvalidQuantityError, InsufficientStockError) as e:
            logger.warning(f"Validation error in update_cart: {e}")
            return build_error_response(e)
        except CartOperationError as e:
            logger.error(f"Operation error in update_cart: {e}")
            return build_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error in update_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при обновлении")
            return build_error_response(error)


class RemoveFromCartView(View):
    """
    Удаление товара из корзины.

    Требует:
    - CSRF token в заголовке X-CSRFToken или в теле запроса
    - variant_id: ID варианта товара

    Возвращает JSON:
    {
        "success": true|false,
        "message": "...",
        "cart_total": общая сумма корзины,
        "cart_items": количество товаров в корзине
    }
    """

    @method_decorator(require_http_methods(["POST"]))
    def dispatch(self, *args, **kwargs):
        """Обрабатывает входящий HTTP-запрос и выбирает нужный метод."""
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Обрабатывает POST-запрос."""
        try:
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            variant_id = CartValidator.validate_remove_item_input(variant_id)

            # Удаляем товар из корзины
            success = CartService.remove_item(request, variant_id)

            if success:
                cart = CartService.get_or_create_cart(request)
                return JsonResponse(
                    {
                        "success": True,
                        "message": "Товар удален из корзины",
                        "cart_total": float(cart.total_price),
                        "cart_items": cart.total_items,
                    }
                )
            else:
                logger.warning(f"Item not found in cart: variant_id {variant_id}")
                return JsonResponse({"success": False, "error": "Товар не найден в корзине"}, status=404)

        except (ProductVariantNotFoundError, InvalidQuantityError) as e:
            logger.warning(f"Validation error in remove_from_cart: {e}")
            return build_error_response(e)
        except CartOperationError as e:
            logger.error(f"Operation error in remove_from_cart: {e}")
            return build_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected error in remove_from_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при удалении товара")
            return build_error_response(error)
