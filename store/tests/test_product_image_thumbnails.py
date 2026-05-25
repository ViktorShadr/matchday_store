from io import BytesIO, StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from store.forms import ProductImageForm
from store.models import Category, Product, ProductImage
from store.services.product_image_thumbnails import ProductImageProcessingError, ProductImageThumbnailService
from store.tasks import generate_product_thumbnail


@override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="sync")
class ProductImageThumbnailFlowTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Тестовая категория изображений")
        self.product = Product.objects.create(name="Тестовый товар", category=self.category)

    @staticmethod
    def _upload_from_image(
        image: Image.Image,
        name: str = "product.png",
        image_format: str = "PNG",
        content_type: str = "image/png",
    ) -> SimpleUploadedFile:
        buffer = BytesIO()
        image.save(buffer, format=image_format)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)

    @staticmethod
    def _assert_color_close(
        test_case: TestCase, pixel: tuple[int, int, int], expected: tuple[int, int, int], delta: int = 35
    ):
        for channel, expected_channel in zip(pixel[:3], expected):
            test_case.assertLessEqual(abs(channel - expected_channel), delta)

    def test_square_image_generates_1200_thumbnail(self):
        upload = self._upload_from_image(Image.new("RGB", (1400, 1400), color=(40, 120, 220)), name="square.png")

        image = ProductImage.objects.create(product=self.product, image=upload, is_primary=True)
        image.refresh_from_db()

        self.assertTrue(bool(image.thumbnail))
        with Image.open(image.thumbnail) as thumbnail:
            self.assertEqual(thumbnail.size, (1200, 1200))

    def test_vertical_image_uses_center_crop(self):
        source = Image.new("RGB", (1000, 1600), color=(0, 255, 0))
        source.paste((255, 0, 0), (0, 0, 1000, 280))
        source.paste((0, 0, 255), (0, 1320, 1000, 1600))
        upload = self._upload_from_image(source, name="vertical.png")

        image = ProductImage.objects.create(product=self.product, image=upload, is_primary=True)
        image.refresh_from_db()

        with Image.open(image.thumbnail) as thumbnail:
            self.assertEqual(thumbnail.size, (1200, 1200))
            self._assert_color_close(self, thumbnail.getpixel((600, 40)), (0, 255, 0))
            self._assert_color_close(self, thumbnail.getpixel((600, 1160)), (0, 255, 0))

    def test_horizontal_image_uses_center_crop(self):
        source = Image.new("RGB", (1600, 1000), color=(0, 255, 0))
        source.paste((255, 0, 0), (0, 0, 280, 1000))
        source.paste((0, 0, 255), (1320, 0, 1600, 1000))
        upload = self._upload_from_image(source, name="horizontal.png")

        image = ProductImage.objects.create(product=self.product, image=upload, is_primary=True)
        image.refresh_from_db()

        with Image.open(image.thumbnail) as thumbnail:
            self.assertEqual(thumbnail.size, (1200, 1200))
            self._assert_color_close(self, thumbnail.getpixel((40, 600)), (0, 255, 0))
            self._assert_color_close(self, thumbnail.getpixel((1160, 600)), (0, 255, 0))

    def test_small_image_is_rejected(self):
        small_upload = self._upload_from_image(Image.new("RGB", (900, 900), color=(255, 255, 255)), name="small.png")
        form = ProductImageForm(data={"alt_text": "small", "is_primary": ""}, files={"image": small_upload})

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn("Изображение слишком маленькое.", str(form.errors["image"]))
        self.assertIn("Минимальный размер: 1000×1000 px.", str(form.errors["image"]))

    def test_thumbnail_is_generated_in_webp_format(self):
        upload = self._upload_from_image(Image.new("RGB", (1300, 1300), color=(10, 60, 180)), name="webp-source.png")

        image = ProductImage.objects.create(product=self.product, image=upload)
        image.refresh_from_db()

        self.assertTrue(image.thumbnail.name.endswith("_1200.webp"))
        with Image.open(image.thumbnail) as thumbnail:
            self.assertEqual(thumbnail.format, "WEBP")

    def test_long_source_name_fits_thumbnail_field_length_limit(self):
        long_name = f"{'x' * 180}.png"
        upload = self._upload_from_image(Image.new("RGB", (1300, 1300), color=(15, 90, 200)), name=long_name)

        image = ProductImage.objects.create(product=self.product, image=upload)
        image.refresh_from_db()

        max_length = ProductImage._meta.get_field("thumbnail").max_length or 100
        self.assertTrue(bool(image.thumbnail.name))
        self.assertLessEqual(len(image.thumbnail.name), max_length)
        self.assertTrue(image.thumbnail.name.startswith("thumbnails/"))
        self.assertTrue(image.thumbnail.name.endswith("_1200.webp"))

    def test_repeat_save_does_not_regenerate_ready_thumbnail(self):
        upload = self._upload_from_image(Image.new("RGB", (1300, 1300), color=(20, 70, 200)), name="stable.png")
        image = ProductImage.objects.create(product=self.product, image=upload)
        image.refresh_from_db()

        self.assertTrue(bool(image.thumbnail))
        thumbnail_name = image.thumbnail.name

        with mock.patch.object(image.thumbnail.storage, "save", side_effect=AssertionError("Unexpected save call")):
            was_processed = ProductImageThumbnailService.ensure_thumbnail(image, force=False)
        self.assertFalse(was_processed)

        image.alt_text = "Обновили только alt"
        image.save(update_fields=["alt_text"])
        image.refresh_from_db()
        self.assertEqual(image.thumbnail.name, thumbnail_name)

    def test_catalog_image_does_not_call_storage_size(self):
        upload = self._upload_from_image(Image.new("RGB", (1300, 1300), color=(20, 90, 210)), name="hot-path.png")
        image = ProductImage.objects.create(product=self.product, image=upload)
        image.refresh_from_db()

        with mock.patch.object(
            image.image.storage,
            "size",
            side_effect=AssertionError("catalog_image must not call storage.size"),
        ):
            self.assertEqual(image.catalog_image.name, image.thumbnail.name)

    def test_metadata_save_is_not_blocked_by_unexpected_thumbnail_errors(self):
        upload = self._upload_from_image(Image.new("RGB", (1300, 1300), color=(30, 90, 200)), name="safe-save.png")
        image = ProductImage.objects.create(product=self.product, image=upload, alt_text="before")

        for error in (OSError("storage unavailable"), NotImplementedError("unsupported operation")):
            with self.subTest(error_type=type(error).__name__):
                updated_alt_text = f"updated-{type(error).__name__}"
                with mock.patch.object(ProductImageThumbnailService, "ensure_thumbnail", side_effect=error):
                    image.alt_text = updated_alt_text
                    image.save(update_fields=["alt_text"])
                image.refresh_from_db()
                self.assertEqual(image.alt_text, updated_alt_text)

    def test_broken_image_is_rejected(self):
        broken_file = SimpleUploadedFile("broken.jpg", b"not an image", content_type="image/jpeg")
        form = ProductImageForm(data={"alt_text": "broken", "is_primary": ""}, files={"image": broken_file})

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn(
            "Загрузите корректный файл изображения.",
            str(form.errors["image"]),
        )

    def test_regenerate_command_uses_failed_label_for_processing_errors(self):
        images = [
            ProductImage.objects.create(
                product=self.product,
                image=self._upload_from_image(
                    Image.new("RGB", (1300, 1300), color=(idx * 20, 80, 120)),
                    name=f"cmd-{idx}.png",
                ),
            )
            for idx in range(3)
        ]
        outcomes = {
            images[0].pk: True,
            images[1].pk: False,
            images[2].pk: ProductImageProcessingError("Изображение слишком маленькое."),
        }

        def ensure_thumbnail_side_effect(product_image, force=False):
            result = outcomes[product_image.pk]
            if isinstance(result, Exception):
                raise result
            return result

        output = StringIO()
        with mock.patch.object(
            ProductImageThumbnailService,
            "ensure_thumbnail",
            side_effect=ensure_thumbnail_side_effect,
        ):
            call_command("regenerate_product_thumbnails", stdout=output)

        command_output = output.getvalue()
        expected_error_line = (
            f"[{images[2].pk}] {self.product.pk} -> failed with error: " "Изображение слишком маленькое."
        )
        self.assertIn(
            expected_error_line,
            command_output,
        )
        self.assertIn("Done: processed=1, skipped=1, failed=1, total=3, force=False", command_output)


class ProductImageThumbnailSignalModeTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Тестовая категория сигналов")
        self.product = Product.objects.create(name="Тестовый товар", category=self.category)

    @staticmethod
    def _upload(name: str = "signal.png", image_format: str = "PNG") -> SimpleUploadedFile:
        buffer = BytesIO()
        Image.new("RGB", (1300, 1300), color=(25, 85, 180)).save(buffer, format=image_format)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    @override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="async")
    def test_signal_enqueues_thumbnail_generation_in_async_mode(self):
        with mock.patch("store.signals.generate_product_thumbnail.delay") as delay_mock:
            with mock.patch("store.signals.ProductImageThumbnailService.ensure_thumbnail") as ensure_mock:
                with self.captureOnCommitCallbacks(execute=True):
                    image = ProductImage.objects.create(product=self.product, image=self._upload())

        delay_mock.assert_called_once_with(image.pk)
        ensure_mock.assert_not_called()

    @override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="sync")
    def test_signal_skips_thumbnail_generation_for_alt_text_only_update(self):
        with mock.patch("store.signals.ProductImageThumbnailService.ensure_thumbnail", return_value=True):
            image = ProductImage.objects.create(product=self.product, image=self._upload(name="initial.png"))

        with mock.patch("store.signals.ProductImageThumbnailService.ensure_thumbnail") as ensure_mock:
            image.alt_text = "Обновили описание"
            image.save(update_fields=["alt_text"])

        ensure_mock.assert_not_called()

    @override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="async")
    def test_signal_keeps_old_thumbnail_path_for_async_cleanup_on_image_replace(self):
        with override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="sync"):
            image = ProductImage.objects.create(product=self.product, image=self._upload(name="before.png"))
        image.refresh_from_db()
        self.assertTrue(bool(image.thumbnail.name))
        old_thumbnail_name = image.thumbnail.name

        with mock.patch("store.signals.generate_product_thumbnail.delay") as delay_mock:
            with self.captureOnCommitCallbacks(execute=True):
                image.image = self._upload(name="after.png")
                image.save(update_fields=["image"])

        image.refresh_from_db()
        self.assertEqual(image.thumbnail.name, old_thumbnail_name)
        self.assertEqual(image.thumbnail_source_name, "")
        self.assertIsNone(image.thumbnail_source_size)
        self.assertEqual(image.catalog_image.name, image.image.name)
        delay_mock.assert_called_once_with(image.pk)

    @override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="async")
    def test_async_regeneration_deletes_old_thumbnail_when_name_changes(self):
        with override_settings(PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE="sync"):
            image = ProductImage.objects.create(product=self.product, image=self._upload(name="before.png"))
        image.refresh_from_db()
        old_thumbnail_name = image.thumbnail.name
        self.assertTrue(image.thumbnail.storage.exists(old_thumbnail_name))

        with mock.patch("store.signals.generate_product_thumbnail.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                image.image = self._upload(name="after.png")
                image.save(update_fields=["image"])

        generate_product_thumbnail(image.pk)

        image.refresh_from_db()
        self.assertNotEqual(image.thumbnail.name, old_thumbnail_name)
        self.assertFalse(image.thumbnail.storage.exists(old_thumbnail_name))
