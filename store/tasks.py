import logging

from celery import shared_task

from store.models import ProductImage
from store.services.product_image_thumbnails import ProductImageProcessingError, ProductImageThumbnailService

logger = logging.getLogger(__name__)


@shared_task(name="store.tasks.generate_product_thumbnail")
def generate_product_thumbnail(product_image_id: int) -> bool:
    """
    Генерирует/обновляет thumbnail для изображения товара.

    Возвращает:
        bool: True, если thumbnail был сгенерирован/обновлен, иначе False.
    """
    try:
        product_image = ProductImage.objects.get(pk=product_image_id)
    except ProductImage.DoesNotExist:
        logger.info("ProductImage id=%s not found while generating thumbnail", product_image_id)
        return False

    if not product_image.image:
        return False

    try:
        return ProductImageThumbnailService.ensure_thumbnail(product_image)
    except ProductImageProcessingError as exc:
        logger.warning(
            "Failed to generate thumbnail for ProductImage id=%s in Celery task: %s",
            product_image_id,
            str(exc),
        )
        return False
    except Exception:
        logger.exception("Unexpected error while generating thumbnail for ProductImage id=%s", product_image_id)
        return False
