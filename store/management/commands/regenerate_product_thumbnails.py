from django.core.management.base import BaseCommand

from store.models import ProductImage
from store.services.product_image_thumbnails import ProductImageProcessingError, ProductImageThumbnailService


class Command(BaseCommand):
    """Регенерирует thumbnail для изображений товаров."""

    help = "Generate/rebuild 1200x1200 WEBP thumbnails for ProductImage records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Пересоздать thumbnail, "
                "даже если уже есть актуальная версия."
            ),
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=100,
            help="Batch size for queryset iterator.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        chunk_size = max(int(options["chunk_size"] or 100), 1)

        processed = 0
        skipped = 0
        failed = 0

        queryset = ProductImage.objects.select_related("product").order_by("pk")
        total = queryset.count()

        self.stdout.write(f"Start thumbnail regeneration for {total} images...")

        for product_image in queryset.iterator(chunk_size=chunk_size):
            try:
                was_processed = ProductImageThumbnailService.ensure_thumbnail(product_image, force=force)
            except ProductImageProcessingError as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"[{product_image.pk}] {product_image.product_id} -> failed with error: {str(exc)}"
                    )
                )
                continue

            if was_processed:
                processed += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: processed={processed}, skipped={skipped}, failed={failed}, total={total}, force={force}"
            )
        )
