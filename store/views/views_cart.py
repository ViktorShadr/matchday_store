import logging
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

from store.application import CartContextResolver
from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()
cart_context_resolver = CartContextResolver()
from store.services.cart_validator import CartValidator
from store.services.cart_exceptions import (
    CartException,
    ProductVariantNotFoundError,
    ProductNotOnSaleError,
    InvalidQuantityError,
    InsufficientStockError,
    CartOperationError,
)

logger = logging.getLogger(__name__)


def should_return_json(request) -> bool:
    """
    Определяет формат ответа на основе заголовков запроса.

    Для обычных браузерных POST-форм (Accept: text/html) возвращаем редирект,
    для AJAX/API-клиентов сохраняем JSON.
    """
    accept = (request.headers.get("Accept") or "").lower()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    accepts_json = "application/json" in accept
    accepts_html = "text/html" in accept

    if is_ajax or accepts_json:
        return True
    return not accepts_html


def get_safe_redirect_url(request, fallback_url_name: str = "store:cart") -> str:
    """Возвращает безопасный URL для редиректа после POST."""
    candidate_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if candidate_url and url_has_allowed_host_and_scheme(
        url=candidate_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate_url
    return reverse(fallback_url_name)


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
        wants_json = should_return_json(request)
        try:
            cart_context = cart_context_resolver.resolve_request(request)
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            quantity_str = request.POST.get("quantity", "1")

            variant_id, quantity = CartValidator.validate_add_to_cart_input(variant_id, quantity_str)

            # Добавляем товар в корзину
            cart_item = cart_service.add_item(cart_context, variant_id, quantity)
            cart = cart_context.cart
            success_message = f'Товар "{cart_item.product_variant.product.name}" добавлен в корзину'

            if wants_json:
                return JsonResponse(
                    {
                        "success": True,
                        "message": success_message,
                        "cart_total": cart.total_items,
                    }
                )
            messages.success(request, success_message)
            return redirect(get_safe_redirect_url(request))

        except (ProductVariantNotFoundError, ProductNotOnSaleError, InvalidQuantityError, InsufficientStockError) as e:
            logger.warning(f"Validation error in add_to_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except CartOperationError as e:
            logger.error(f"Operation error in add_to_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except Exception as e:
            logger.error(f"Unexpected error in add_to_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при добавлении товара")
            if wants_json:
                return build_error_response(error)
            messages.error(request, str(error))
            return redirect(get_safe_redirect_url(request))


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
        wants_json = should_return_json(request)
        try:
            cart_context = cart_context_resolver.resolve_request(request)
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            quantity_str = request.POST.get("quantity", "1")

            variant_id, quantity = CartValidator.validate_update_quantity_input(variant_id, quantity_str)

            # Обновляем товар в корзине
            cart_item = cart_service.update_item_quantity(cart_context, variant_id, quantity)
            cart = cart_context.cart
            success_message = "Количество товара обновлено"

            if wants_json:
                return JsonResponse(
                    {
                        "success": True,
                        "message": success_message,
                        "item_total": float(cart_item.total_price),
                        "item_quantity": cart_item.quantity,
                        "cart_total": float(cart.total_price),
                        "cart_items": cart.total_items,
                    }
                )
            messages.success(request, success_message)
            return redirect(get_safe_redirect_url(request))

        except (ProductVariantNotFoundError, ProductNotOnSaleError, InvalidQuantityError, InsufficientStockError) as e:
            logger.warning(f"Validation error in update_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except CartOperationError as e:
            logger.error(f"Operation error in update_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except Exception as e:
            logger.error(f"Unexpected error in update_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при обновлении")
            if wants_json:
                return build_error_response(error)
            messages.error(request, str(error))
            return redirect(get_safe_redirect_url(request))


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
        wants_json = should_return_json(request)
        try:
            cart_context = cart_context_resolver.resolve_request(request)
            # Валидируем входные данные
            variant_id = request.POST.get("variant_id")
            variant_id = CartValidator.validate_remove_item_input(variant_id)

            # Удаляем товар из корзины
            success = cart_service.remove_item(cart_context, variant_id)

            if success:
                cart = cart_context.cart
                success_message = "Товар удален из корзины"
                if wants_json:
                    return JsonResponse(
                        {
                            "success": True,
                            "message": success_message,
                            "cart_total": float(cart.total_price),
                            "cart_items": cart.total_items,
                        }
                    )
                messages.success(request, success_message)
                return redirect(get_safe_redirect_url(request))

            logger.warning(f"Item not found in cart: variant_id {variant_id}")
            if wants_json:
                return JsonResponse({"success": False, "error": "Товар не найден в корзине"}, status=404)
            messages.warning(request, "Товар не найден в корзине")
            return redirect(get_safe_redirect_url(request))

        except (ProductVariantNotFoundError, InvalidQuantityError) as e:
            logger.warning(f"Validation error in remove_from_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except CartOperationError as e:
            logger.error(f"Operation error in remove_from_cart: {e}")
            if wants_json:
                return build_error_response(e)
            messages.error(request, str(e))
            return redirect(get_safe_redirect_url(request))
        except Exception as e:
            logger.error(f"Unexpected error in remove_from_cart: {e}", exc_info=True)
            error = CartOperationError("Произошла ошибка при удалении товара")
            if wants_json:
                return build_error_response(error)
            messages.error(request, str(error))
            return redirect(get_safe_redirect_url(request))
