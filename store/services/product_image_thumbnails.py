from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from store.models import ProductImage


class ProductImageProcessingError(Exception):
    """Ошибка обработки изображения товара."""


class ProductImageThumbnailService:
    """Сервис валидации и генерации thumbnail для изображений товара."""

    THUMBNAIL_WIDTH = 1200
    THUMBNAIL_HEIGHT = 1200
    THUMBNAIL_QUALITY = 85
    THUMBNAIL_FORMAT = "WEBP"
    MIN_WIDTH = 1000
    MIN_HEIGHT = 1000
    MAX_DIMENSION = 10000

    INVALID_IMAGE_MESSAGE = "Загрузите корректный файл изображения."
    SMALL_IMAGE_MESSAGE = "Изображение слишком маленькое.\nМинимальный размер: 1000×1000 px."
    LARGE_IMAGE_MESSAGE = "Изображение слишком большое. Максимальный размер: 10000×10000 px."

    @classmethod
    def validate_image_file(cls, image_file) -> None:
        """
        Проверяет, что файл изображения целый и проходит ограничения по размерам.
        """
        cls._ensure_image_integrity(image_file)
        width, height = cls._read_image_dimensions(image_file)
        cls._validate_dimensions(width, height)

    @classmethod
    def ensure_thumbnail(cls, product_image: ProductImage, force: bool = False) -> bool:
        """
        Гарантирует наличие актуального thumbnail.

        Returns:
            bool: True, если thumbnail был сгенерирован/пересоздан, иначе False.
        """
        if not product_image.image:
            return False

        current_size = cls._safe_file_size(product_image.image)
        if not force and cls._is_thumbnail_up_to_date(product_image, current_size):
            return False

        thumbnail_content = cls._build_thumbnail_content(product_image.image)
        thumbnail_name = cls._build_thumbnail_name(product_image.image.name, product_image.pk)
        saved_thumbnail_name = cls._save_thumbnail_file(product_image, thumbnail_name, thumbnail_content)

        ProductImage.objects.filter(pk=product_image.pk).update(
            thumbnail=saved_thumbnail_name,
            thumbnail_source_name=product_image.image.name,
            thumbnail_source_size=current_size,
        )
        product_image.thumbnail.name = saved_thumbnail_name
        product_image.thumbnail_source_name = product_image.image.name
        product_image.thumbnail_source_size = current_size
        return True

    @classmethod
    def _build_thumbnail_content(cls, image_file) -> bytes:
        cls.validate_image_file(image_file)
        cls._reset_file_pointer(image_file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image_file) as opened_image:
                    normalized = ImageOps.exif_transpose(opened_image)
                    normalized = cls._normalize_mode(normalized)
                    prepared = ImageOps.fit(
                        normalized,
                        (cls.THUMBNAIL_WIDTH, cls.THUMBNAIL_HEIGHT),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )

                    output_buffer = BytesIO()
                    prepared.save(
                        output_buffer,
                        format=cls.THUMBNAIL_FORMAT,
                        quality=cls.THUMBNAIL_QUALITY,
                        optimize=True,
                    )
                    return output_buffer.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ProductImageProcessingError(cls.INVALID_IMAGE_MESSAGE) from exc
        finally:
            cls._reset_file_pointer(image_file)

    @classmethod
    def _save_thumbnail_file(cls, product_image: ProductImage, target_name: str, content: bytes) -> str:
        storage = product_image.thumbnail.storage
        old_name = product_image.thumbnail.name
        if old_name and old_name != target_name:
            storage.delete(old_name)
        if storage.exists(target_name):
            storage.delete(target_name)
        return storage.save(target_name, ContentFile(content))

    @classmethod
    def _is_thumbnail_up_to_date(cls, product_image: ProductImage, current_size: int | None) -> bool:
        thumbnail_name = product_image.thumbnail.name
        if not thumbnail_name:
            return False
        if product_image.thumbnail_source_name != product_image.image.name:
            return False
        if product_image.thumbnail_source_size != current_size:
            return False
        try:
            return bool(product_image.thumbnail.storage.exists(thumbnail_name))
        except OSError:
            return False

    @classmethod
    def _safe_file_size(cls, image_field) -> int | None:
        try:
            return int(image_field.size)
        except (OSError, ValueError, TypeError):
            return None

    @classmethod
    def _build_thumbnail_name(cls, original_name: str, image_id: int | None) -> str:
        stem = Path(original_name).stem or "product_image"
        normalized_stem = stem.replace(" ", "_")
        suffix = str(image_id) if image_id is not None else "img"
        return f"thumbnails/{normalized_stem}_{suffix}_{cls.THUMBNAIL_WIDTH}.webp"

    @classmethod
    def _ensure_image_integrity(cls, image_file) -> None:
        cls._reset_file_pointer(image_file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image_file) as opened_image:
                    opened_image.verify()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ProductImageProcessingError(cls.INVALID_IMAGE_MESSAGE) from exc
        finally:
            cls._reset_file_pointer(image_file)

    @classmethod
    def _read_image_dimensions(cls, image_file) -> tuple[int, int]:
        cls._reset_file_pointer(image_file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image_file) as opened_image:
                    oriented_image = ImageOps.exif_transpose(opened_image)
                    return oriented_image.size
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ProductImageProcessingError(cls.INVALID_IMAGE_MESSAGE) from exc
        finally:
            cls._reset_file_pointer(image_file)

    @classmethod
    def _validate_dimensions(cls, width: int, height: int) -> None:
        if width < cls.MIN_WIDTH or height < cls.MIN_HEIGHT:
            raise ProductImageProcessingError(cls.SMALL_IMAGE_MESSAGE)
        if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
            raise ProductImageProcessingError(cls.LARGE_IMAGE_MESSAGE)

    @classmethod
    def _normalize_mode(cls, image: Image.Image) -> Image.Image:
        if image.mode in {"RGB", "RGBA"}:
            return image
        if "A" in image.getbands():
            return image.convert("RGBA")
        return image.convert("RGB")

    @staticmethod
    def _reset_file_pointer(image_file) -> None:
        try:
            image_file.seek(0)
        except (AttributeError, OSError, ValueError):
            return
