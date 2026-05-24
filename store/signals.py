import logging

from django.conf import settings
from django.contrib.auth import user_logged_in
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from store.application import CartContextResolver
from store.models import ProductImage
from store.services.cart_service import CartService
from store.services.product_image_thumbnails import ProductImageProcessingError, ProductImageThumbnailService
from store.tasks import generate_product_thumbnail

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()
cart_context_resolver = CartContextResolver()
logger = logging.getLogger(__name__)

THUMBNAIL_RELATED_UPDATE_FIELDS = frozenset({"image", "thumbnail", "thumbnail_source_name", "thumbnail_source_size"})


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


def _should_process_thumbnail(created: bool, update_fields) -> bool:
    if created:
        return True
    if update_fields is None:
        return True
    return bool(set(update_fields).intersection(THUMBNAIL_RELATED_UPDATE_FIELDS))


def _enqueue_thumbnail_generation(product_image_id: int) -> None:
    def enqueue_thumbnail_task():
        try:
            generate_product_thumbnail.delay(product_image_id)
        except Exception:
            logger.exception(
                "Не удалось отправить задачу генерации thumbnail для ProductImage id=%s",
                product_image_id,
            )

    transaction.on_commit(enqueue_thumbnail_task)


def _ensure_thumbnail_sync(instance: ProductImage) -> None:
    try:
        ProductImageThumbnailService.ensure_thumbnail(instance)
    except ProductImageProcessingError as exc:
        logger.warning("Не удалось подготовить thumbnail для ProductImage id=%s: %s", instance.pk, str(exc))
    except Exception:
        logger.exception(
            "Неожиданная ошибка при подготовке thumbnail для ProductImage id=%s",
            instance.pk,
        )


@receiver(post_save, sender=ProductImage)
def ensure_product_thumbnail(
    sender,
    instance: ProductImage,
    created: bool = False,
    raw: bool = False,
    update_fields=None,
    **kwargs,
):
    """
    Поддерживает thumbnail в актуальном состоянии при сохранении изображения.

    Ошибки обработки логируются и не блокируют основное сохранение объекта.
    """
    if raw:
        return
    if not instance.image:
        return
    if not _should_process_thumbnail(created, update_fields):
        return

    generation_mode = getattr(settings, "PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE", "sync")
    if generation_mode == "async":
        _enqueue_thumbnail_generation(instance.pk)
        return

    _ensure_thumbnail_sync(instance)
