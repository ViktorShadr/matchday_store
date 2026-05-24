from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from store.forms import ProductImageForm
from store.models import Category, Product, ProductImage
from store.services.product_image_thumbnails import ProductImageThumbnailService


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

    def test_broken_image_is_rejected(self):
        broken_file = SimpleUploadedFile("broken.jpg", b"not an image", content_type="image/jpeg")
        form = ProductImageForm(data={"alt_text": "broken", "is_primary": ""}, files={"image": broken_file})

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn("Загрузите корректный файл изображения.", str(form.errors["image"]))
