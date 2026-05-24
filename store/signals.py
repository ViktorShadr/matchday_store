import logging

from django.contrib.auth import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from store.application import CartContextResolver
from store.models import ProductImage
from store.services.cart_service import CartService
from store.services.product_image_thumbnails import ProductImageProcessingError, ProductImageThumbnailService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()
cart_context_resolver = CartContextResolver()
logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def merge_carts_on_login(sender, request, user, **kwargs):
    """
    Объединяет корзины при входе пользователя в систему.

    Получает session_key ДО авторизации (сохраненный в _pre_login_session_key)
    или использует текущий session_key для поиска сессионной корзины.
    """
    # Получаем session_key ДО авторизации (если есть)
    session_key = request.session.get("_pre_login_session_key")

    # Если не найден, используем текущий session_key
    # (это может помочь в некоторых случаях)
    if not session_key and request.session.session_key:
        session_key = request.session.session_key

    if session_key:
        # Очищаем сохраненный session_key из сессии
        if "_pre_login_session_key" in request.session:
            del request.session["_pre_login_session_key"]
            request.session.modified = True

        cart_context_resolver.merge_on_login(user, session_key)


@receiver(post_save, sender=ProductImage)
def ensure_product_thumbnail(sender, instance: ProductImage, raw: bool = False, **kwargs):
    """
    Поддерживает thumbnail в актуальном состоянии при сохранении изображения.

    Ошибки обработки логируются и не блокируют основное сохранение объекта.
    """
    if raw:
        return
    if not instance.image:
        return

    try:
        ProductImageThumbnailService.ensure_thumbnail(instance)
    except ProductImageProcessingError as exc:
        logger.warning("Не удалось подготовить thumbnail для ProductImage id=%s: %s", instance.pk, str(exc))
