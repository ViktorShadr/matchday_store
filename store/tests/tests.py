from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from orders.models import Order, OrderItem, OrderStatusTransition
from payments.models import Payment
from store.application import CartContext, CartContextResolver
from store.forms import ProductImageForm, ProductVariantForm
from store.models import Cart, CartItem, Category, Page, Product, ProductImage, ProductVariant
from store.presenters.catalog_presenters import ProductCardPresenter
from store.services import InsufficientStockError, ProductNotOnSaleError
from store.services.cart_service import CartService
from users.models import User


class CategoryModelTest(TestCase):
    """Тесты для CategoryModelTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.category = Category.objects.create(name="Одежда", description="Одежда для спорта")

    def test_category_creation(self):
        """Проверяет сценарий 'category creation'."""
        self.assertEqual(self.category.name, "Одежда")
        self.assertEqual(self.category.description, "Одежда для спорта")
        self.assertTrue(self.category.created_at)
        self.assertTrue(self.category.updated_at)

    def test_category_str_method(self):
        """Проверяет сценарий 'category str method'."""
        self.assertEqual(str(self.category), "Одежда")

    def test_category_unique_name(self):
        """Проверяет сценарий 'category unique name'."""
        with self.assertRaises(Exception):
            Category.objects.create(name="Одежда")


class ProductModelTest(TestCase):
    """Тесты для ProductModelTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.category = Category.objects.create(name="Футболки", description="Спортивные футболки")
        self.product = Product.objects.create(
            name="Футболка ФК Шинник",
            description="Официальная футболка домашнего комплекта",
            category=self.category,
        )

    def test_product_creation(self):
        """Проверяет сценарий 'product creation'."""
        self.assertEqual(self.product.name, "Футболка ФК Шинник")
        self.assertEqual(self.product.category, self.category)
        self.assertEqual(self.product.short_description, "")
        self.assertIsNone(self.product.old_price)
        self.assertEqual(self.product.material, "")
        self.assertTrue(self.product.is_on_sale)
        self.assertTrue(self.product.created_at)
        self.assertTrue(self.product.updated_at)

    def test_product_str_method(self):
        """Проверяет сценарий 'product str method'."""
        self.assertEqual(str(self.product), "Футболка ФК Шинник")

    def test_product_without_category(self):
        """Проверяет сценарий 'product without category'."""
        product_no_category = Product.objects.create(name="Футболка без категории", description="Тестовый товар")
        self.assertIsNone(product_no_category.category)


class ProductImageModelTest(TestCase):
    """Тесты для ProductImageModelTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(
            product=self.product, image=test_image, alt_text="Тестовое изображение", is_primary=True
        )

    def test_product_image_creation(self):
        """Проверяет сценарий 'product image creation'."""
        self.assertEqual(self.image.product, self.product)
        self.assertEqual(self.image.alt_text, "Тестовое изображение")
        self.assertTrue(self.image.is_primary)

    def test_product_image_str_method(self):
        """Проверяет сценарий 'product image str method'."""
        expected = "Изображение для Тестовая футболка"
        self.assertEqual(str(self.image), expected)


class ProductImageFormValidationTest(TestCase):
    """Тесты ограничений загрузки изображений товара."""

    @staticmethod
    def _image_upload(name="product.png", content_type="image/png", extra_bytes=b"", size=(1200, 1200)):
        image_buffer = BytesIO()
        Image.new("RGB", size, color="white").save(image_buffer, format="PNG")
        return SimpleUploadedFile(name, image_buffer.getvalue() + extra_bytes, content_type=content_type)

    def test_accepts_valid_image(self):
        form = ProductImageForm(
            data={"alt_text": "Фото товара", "is_primary": "on"},
            files={"image": self._image_upload()},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_file_above_size_limit(self):
        form = ProductImageForm(
            data={"alt_text": "Большое фото", "is_primary": ""},
            files={"image": self._image_upload(extra_bytes=b"0" * ProductImageForm.MAX_FILE_SIZE)},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn("Размер изображения", str(form.errors["image"]))

    def test_rejects_spoofed_non_image_file(self):
        form = ProductImageForm(
            data={"alt_text": "Не фото", "is_primary": ""},
            files={"image": SimpleUploadedFile("product.jpg", b"not an image", content_type="image/jpeg")},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_rejects_disallowed_extension(self):
        form = ProductImageForm(
            data={"alt_text": "Файл", "is_primary": ""},
            files={"image": self._image_upload(name="product.bmp", content_type="image/png")},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertIn("Допустимые форматы", str(form.errors["image"]))


class ProductVariantModelTest(TestCase):
    """Тесты для ProductVariantModelTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="TSHIRT-RED-L",
            size="L",
            color="Красный",
            price=Decimal("2999.99"),
            quantity=10,
            image=self.image,
        )

    def test_product_variant_creation(self):
        """Проверяет сценарий 'product variant creation'."""
        self.assertEqual(self.variant.product, self.product)
        self.assertEqual(self.variant.sku, "TSHIRT-RED-L")
        self.assertEqual(self.variant.size, "L")
        self.assertEqual(self.variant.color, "Красный")
        self.assertEqual(self.variant.price, Decimal("2999.99"))
        self.assertEqual(self.variant.quantity, 10)
        self.assertEqual(self.variant.image, self.image)

    def test_product_variant_str_method(self):
        """Проверяет сценарий 'product variant str method'."""
        expected = "Тестовая футболка (L, Красный)"
        self.assertEqual(str(self.variant), expected)

    def test_product_variant_unique_constraint(self):
        """Проверяет сценарий 'product variant unique constraint'."""
        with self.assertRaises(Exception):
            ProductVariant.objects.create(
                product=self.product, size="L", color="Красный", price=Decimal("1999.99"), quantity=5, image=self.image
            )

    def test_product_variant_rejects_duplicate_nonblank_sku(self):
        """Непустой SKU должен быть уникальным между вариантами."""
        with self.assertRaises(Exception):
            ProductVariant.objects.create(
                product=self.product,
                sku="TSHIRT-RED-L",
                size="XL",
                color="Красный",
                price=Decimal("2999.99"),
                quantity=5,
                image=self.image,
            )

    def test_product_variant_price_validator_rejects_non_positive_values(self):
        """Проверяет сценарий 'product variant price validator'."""
        invalid_prices = [Decimal("-100"), Decimal("0.00")]
        for price in invalid_prices:
            with self.subTest(price=price):
                variant = ProductVariant(
                    product=self.product,
                    size="M",
                    color="Синий",
                    price=price,
                    quantity=5,
                    image=self.image,
                )
                with self.assertRaises(ValidationError):
                    variant.full_clean()

    def test_product_variant_form_rejects_zero_price(self):
        form = ProductVariantForm(
            data={
                "sku": "TSHIRT-BLUE-M",
                "size": "M",
                "color": "Синий",
                "price": "0.00",
                "quantity": "5",
                "image": "",
            },
            product=self.product,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_product_variant_form_trims_sku(self):
        form = ProductVariantForm(
            data={
                "sku": "  TSHIRT-BLUE-M  ",
                "size": "M",
                "color": "Синий",
                "price": "1999.00",
                "quantity": "5",
                "image": "",
            },
            product=self.product,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sku"], "TSHIRT-BLUE-M")


class ProductCardPresenterTest(TestCase):
    """Тесты подготовки карточки товара."""

    def setUp(self):
        self.category = Category.objects.create(name="Карточки товаров")

    def test_single_available_variant_can_be_added_from_card(self):
        """Если доступен один вариант, карточка сразу добавляет его в корзину."""
        product = Product.objects.create(name="Футболка с одним доступным размером", category=self.category)
        available_variant = ProductVariant.objects.create(
            product=product,
            size="M",
            color="Синий",
            price=Decimal("1999.00"),
            quantity=3,
        )
        ProductVariant.objects.create(
            product=product,
            size="L",
            color="Синий",
            price=Decimal("1999.00"),
            quantity=0,
        )

        enriched = ProductCardPresenter.enrich(product)

        self.assertEqual(enriched.variant_count, 2)
        self.assertEqual(enriched.available_variant_count, 1)
        self.assertFalse(enriched.requires_variant_selection)
        self.assertEqual(enriched.card_cta_action, "cart")
        self.assertEqual(enriched.card_cta_label, "В корзину")
        self.assertEqual(enriched.first_available_variant_id, available_variant.id)

    def test_multiple_available_variants_open_detail_selection(self):
        """Если доступны несколько вариантов, карточка ведет к выбору варианта."""
        product = Product.objects.create(name="Футболка с размерами", category=self.category)
        ProductVariant.objects.create(
            product=product,
            size="M",
            color="Черный",
            price=Decimal("1999.00"),
            quantity=2,
        )
        ProductVariant.objects.create(
            product=product,
            size="L",
            color="Черный",
            price=Decimal("1999.00"),
            quantity=2,
        )

        enriched = ProductCardPresenter.enrich(product)

        self.assertEqual(enriched.available_variant_count, 2)
        self.assertTrue(enriched.requires_variant_selection)
        self.assertEqual(enriched.card_cta_action, "detail")
        self.assertEqual(enriched.card_cta_label, "Выбрать размер")


class MainViewTest(TestCase):
    """Тесты для MainViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(
            name="Тестовая футболка", description="Описание товара", category=self.category
        )
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image, is_primary=True)
        self.variant = ProductVariant.objects.create(
            product=self.product, size="L", color="Красный", price=Decimal("2999.99"), quantity=10, image=self.image
        )

    def test_main_view_status_code(self):
        """Проверяет сценарий 'main view status code'."""
        response = self.client.get(reverse("store:base"))
        self.assertEqual(response.status_code, 200)

    def test_main_view_template(self):
        """Проверяет сценарий 'main view template'."""
        response = self.client.get(reverse("store:base"))
        self.assertTemplateUsed(response, "main_page/index.html")

    def test_main_view_context(self):
        """Проверяет сценарий 'main view context'."""
        response = self.client.get(reverse("store:base"))
        self.assertIn("categories", response.context)
        self.assertIn("popular_products", response.context)
        self.assertEqual(len(response.context["categories"]), 1)
        self.assertEqual(len(response.context["popular_products"]), 1)

    def test_main_view_shows_swipe_gallery_when_product_has_multiple_images(self):
        """Карточка на главной должна показывать все фото товара в свайп-галерее."""
        self.image.is_primary = False
        self.image.save(update_fields=["is_primary"])
        primary_image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("main-primary-image.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )

        response = self.client.get(reverse("store:base"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, primary_image.image.url)
        self.assertContains(response, self.image.image.url)
        self.assertContains(response, "data-sf-product-swiper")
        detail_url = reverse("store:product_detail", kwargs={"pk": self.product.pk})
        self.assertContains(
            response,
            f'href="{detail_url}" class="swiper-slide sf-product-card-image-link"',
            count=2,
        )


class ProductListViewTest(TestCase):
    """Тесты для ProductListViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.category = Category.objects.create(name="Футболки")

        for i in range(15):
            product = Product.objects.create(
                name=f"Футболка {i}", description=f"Описание футболки {i}", category=self.category
            )
            # Создаем тестовое изображение
            test_image = SimpleUploadedFile(f"test_image_{i}.jpg", b"fake_image_data", content_type="image/jpeg")
            image = ProductImage.objects.create(product=product, image=test_image, is_primary=True)
            ProductVariant.objects.create(
                product=product,
                size="L",
                color="Красный",
                price=Decimal("1000.00") + Decimal(i),
                quantity=10,
                image=image,
            )

    def test_product_list_view_status_code(self):
        """Проверяет сценарий 'product list view status code'."""
        response = self.client.get(reverse("store:product_list"))
        self.assertEqual(response.status_code, 200)

    def test_product_list_view_template(self):
        """Проверяет сценарий 'product list view template'."""
        response = self.client.get(reverse("store:product_list"))
        self.assertTemplateUsed(response, "main_page/product_list.html")

    def test_product_list_view_context(self):
        """Проверяет сценарий 'product list view context'."""
        response = self.client.get(reverse("store:product_list"))
        self.assertIn("products", response.context)
        self.assertIn("categories", response.context)
        self.assertEqual(len(response.context["products"]), 12)  # paginate_by = 12

    def test_product_list_pagination(self):
        """Проверяет сценарий 'product list pagination'."""
        response = self.client.get(reverse("store:product_list") + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 3)

    def test_product_list_sort_by_price_asc(self):
        """Список должен сортироваться по цене по возрастанию."""
        response = self.client.get(reverse("store:product_list"), {"sort": "price_asc"})

        self.assertEqual(response.status_code, 200)
        prices = [product.display_price for product in response.context["products"]]
        self.assertEqual(prices, sorted(prices))

    def test_product_list_sort_by_price_desc(self):
        """Список должен сортироваться по цене по убыванию."""
        response = self.client.get(reverse("store:product_list"), {"sort": "price_desc"})

        self.assertEqual(response.status_code, 200)
        prices = [product.display_price for product in response.context["products"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_product_list_price_sort_uses_in_stock_display_price(self):
        """Сортировка по цене должна учитывать ту же доступную цену, что и карточка товара."""
        lower_priced_product = Product.objects.get(name="Футболка 1")
        conflicted_product = Product.objects.get(name="Футболка 0")

        conflicted_variant = conflicted_product.variants.get()
        conflicted_variant.quantity = 0
        conflicted_variant.save(update_fields=["quantity", "updated_at"])

        ProductVariant.objects.create(
            product=conflicted_product,
            size="XL",
            color="Синий",
            price=Decimal("1005.00"),
            quantity=10,
            image=conflicted_variant.image,
        )

        response = self.client.get(reverse("store:product_list"), {"sort": "price_asc"})

        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        lower_priced_index = next(
            index for index, product in enumerate(products) if product.pk == lower_priced_product.pk
        )
        conflicted_index = next(index for index, product in enumerate(products) if product.pk == conflicted_product.pk)
        self.assertLess(lower_priced_index, conflicted_index)
        self.assertEqual(
            next(product.display_price for product in products if product.pk == conflicted_product.pk),
            Decimal("1005.00"),
        )

    def test_product_list_sort_by_name_asc(self):
        """Список должен сортироваться по названию А-Я."""
        response = self.client.get(reverse("store:product_list"), {"sort": "name_asc"})

        self.assertEqual(response.status_code, 200)
        names = [product.name for product in response.context["products"]]
        self.assertEqual(names, sorted(names))

    def test_product_list_sort_by_name_desc(self):
        """Список должен сортироваться по названию Я-А."""
        response = self.client.get(reverse("store:product_list"), {"sort": "name_desc"})

        self.assertEqual(response.status_code, 200)
        names = [product.name for product in response.context["products"]]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_product_list_shows_out_of_stock_status(self):
        """Товар без остатков должен маркироваться как отсутствующий."""
        visible_product = Product.objects.order_by("-created_at").first()
        visible_product.variants.update(quantity=0)

        response = self.client.get(reverse("store:product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нет в наличии")

    def test_product_list_hides_products_not_on_sale(self):
        """Товары со снятой продажей не должны отображаться в каталоге."""
        hidden_product = Product.objects.create(
            name="Скрытый товар",
            description="Не должен быть виден на витрине",
            category=self.category,
            is_on_sale=False,
        )
        hidden_image = ProductImage.objects.create(
            product=hidden_product,
            image=SimpleUploadedFile("hidden.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        ProductVariant.objects.create(
            product=hidden_product,
            size="L",
            color="Черный",
            price=Decimal("1999.00"),
            quantity=10,
            image=hidden_image,
        )

        response = self.client.get(reverse("store:product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Скрытый товар")

    def test_product_list_filters_by_size_stock_price_and_sku(self):
        """Каталог должен фильтровать товары по размеру, наличию, цене и SKU."""
        target_product = Product.objects.create(
            name="Матчевая футболка",
            short_description="Игровая форма",
            description="Футболка для матча",
            category=self.category,
        )
        target_variant = ProductVariant.objects.create(
            product=target_product,
            sku="MATCHDAY-M-001",
            size="M",
            color="Синий",
            price=Decimal("2490.00"),
            quantity=3,
        )
        out_of_stock_product = Product.objects.create(
            name="Тренировочная футболка",
            description="Нет в наличии",
            category=self.category,
        )
        ProductVariant.objects.create(
            product=out_of_stock_product,
            sku="TRAINING-M-001",
            size="M",
            color="Синий",
            price=Decimal("2390.00"),
            quantity=0,
        )

        response = self.client.get(
            reverse("store:product_list"),
            {
                "q": "футболка",
                "size": "M",
                "in_stock": "1",
                "price_min": "2000",
                "price_max": "2600",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target_product.name)
        self.assertContains(response, "Размер: M")
        self.assertContains(response, "Только в наличии")
        self.assertNotContains(response, out_of_stock_product.name)

        sku_response = self.client.get(reverse("store:product_list"), {"q": target_variant.sku})
        self.assertContains(sku_response, target_product.name)


class ProductDetailsViewTest(TestCase):
    """Тесты для ProductDetailsViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(
            name="Тестовая футболка", description="Описание товара", category=self.category
        )
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image, is_primary=True)
        self.variant = ProductVariant.objects.create(
            product=self.product, size="L", color="Красный", price=Decimal("2999.99"), quantity=10, image=self.image
        )

    def test_product_detail_view_status_code(self):
        """Проверяет сценарий 'product detail view status code'."""
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_detail_view_template(self):
        """Проверяет сценарий 'product detail view template'."""
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_details.html")

    def test_product_detail_view_context(self):
        """Проверяет сценарий 'product detail view context'."""
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertIn("product", response.context)
        self.assertIn("product_images", response.context)
        self.assertIn("variants", response.context)
        self.assertEqual(response.context["product"], self.product)

    def test_product_detail_view_404(self):
        """Проверяет сценарий 'product detail view 404'."""
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)

    def test_product_detail_shows_out_of_stock_status(self):
        """На странице товара должен отображаться статус отсутствия."""
        self.variant.quantity = 0
        self.variant.save(update_fields=["quantity"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нет в наличии")
        self.assertContains(response, "Временно недоступно")
        self.assertNotContains(response, "data-sf-product-buy-form")

    def test_product_detail_single_variant_hides_exact_stock_when_plenty_available(self):
        """Один вариант с большим остатком показывает только общий статус наличия."""
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "В наличии")
        self.assertContains(response, "Размер: L · Цвет: Красный")
        self.assertNotContains(response, "Осталось мало")
        self.assertNotContains(response, "Последний товар")
        self.assertNotContains(response, "В наличии:")

    def test_product_detail_single_variant_shows_low_stock_badge(self):
        """Один вариант с остатком 2-5 показывает мягкое предупреждение без точного количества."""
        self.variant.quantity = 3
        self.variant.save(update_fields=["quantity"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Осталось мало")
        self.assertNotContains(response, "3 шт.")

    def test_product_detail_single_variant_shows_last_item_badge(self):
        """Один вариант с остатком 1 показывает отдельный badge."""
        self.variant.quantity = 1
        self.variant.save(update_fields=["quantity"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Последний товар")
        self.assertNotContains(response, "1 шт.")

    def test_product_detail_multiple_variants_uses_clean_option_labels_and_stock_data(self):
        """Select вариантов не показывает SKU и точные остатки, но хранит остаток для JS."""
        self.variant.quantity = 3
        self.variant.sku = "DETAIL-L-001"
        self.variant.save(update_fields=["quantity", "sku", "updated_at"])
        ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("3499.00"),
            quantity=1,
            image=self.image,
            sku="DETAIL-M-002",
        )

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "L / Красный")
        self.assertContains(response, "M / Синий")
        self.assertContains(response, "3499 ₽")
        self.assertContains(response, 'data-available-quantity="3"')
        self.assertContains(response, 'data-available-quantity="1"')
        self.assertContains(response, "Осталось мало")
        self.assertNotContains(response, "DETAIL-L-001")
        self.assertNotContains(response, "DETAIL-M-002")
        self.assertNotContains(response, "3 шт.")
        self.assertNotContains(response, "1 шт.")

    def test_product_detail_uses_primary_image_as_main(self):
        """Детальная страница должна показывать основное изображение в главном блоке."""
        self.image.is_primary = False
        self.image.save(update_fields=["is_primary"])
        primary_image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("details-primary-image.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_gallery_images"][0]["url"], primary_image.image.url)
        self.assertContains(response, primary_image.image.url)

    def test_product_detail_enables_swipe_gallery_for_multiple_images(self):
        """При нескольких фото на детальной странице должен включаться свайп-режим."""
        ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("details-secondary-image.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=False,
        )

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-sf-product-detail-gallery")
        self.assertContains(response, 'data-sf-gallery-count="2"')
        self.assertContains(response, "data-sf-product-detail-main")
        self.assertContains(response, "data-sf-product-detail-thumbs")

    def test_product_detail_shows_commercial_fields_and_hides_public_variant_sku(self):
        """Карточка товара показывает коммерческие атрибуты, но не публичный SKU варианта."""
        self.product.short_description = "Короткое описание для карточки"
        self.product.old_price = Decimal("3499.00")
        self.product.material = "Хлопок 100%"
        self.product.size_guide = "L: 50-52"
        self.product.care_instructions = "Стирать при 30 градусах"
        self.product.save(
            update_fields=[
                "short_description",
                "old_price",
                "material",
                "size_guide",
                "care_instructions",
                "updated_at",
            ]
        )
        self.variant.sku = "DETAIL-L-001"
        self.variant.save(update_fields=["sku", "updated_at"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Короткое описание для карточки")
        self.assertContains(response, "3499,00 ₽")
        self.assertNotContains(response, "DETAIL-L-001")
        self.assertContains(response, "Хлопок 100%")
        self.assertContains(response, "Размерная сетка")
        self.assertContains(response, "Стирать при 30 градусах")

    def test_product_detail_view_404_when_product_not_on_sale(self):
        """Снятый с продажи товар не должен открываться на витрине."""
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 404)


class ModeratorDashboardAccessTest(TestCase):
    """Тесты доступа к модераторскому дашборду и складу."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="user@example.com", password="testpass123", is_active=True)
        self.staff_without_group = User.objects.create_user(
            email="staff-no-group@example.com",
            password="testpass123",
            is_staff=True,
            is_active=True,
        )
        self.superuser = User.objects.create_superuser(email="root@example.com", password="rootpass123")
        self.moderator = User.objects.create_user(
            email="mod@example.com", password="modpass123", is_staff=True, is_active=True
        )
        self.group_only_user = User.objects.create_user(
            email="group-only@example.com",
            password="modpass123",
            is_active=True,
        )
        moderator_group = Group.objects.create(name="Модераторы")
        self.moderator.groups.add(moderator_group)
        self.group_only_user.groups.add(moderator_group)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 302)

    def test_dashboard_forbidden_for_regular_user(self):
        self.client.login(email="user@example.com", password="testpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_available_for_group_moderator(self):
        self.client.login(email="mod@example.com", password="modpass123")

        response = self.client.get(reverse("store:dashboard_home"), follow=True)

        self.assertRedirects(response, reverse("store:warehouse_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Склад")

    def test_dashboard_forbidden_for_staff_without_moderator_group(self):
        self.client.login(email="staff-no-group@example.com", password="testpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_forbidden_for_group_user_without_staff(self):
        self.client.login(email="group-only@example.com", password="modpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_available_for_superuser(self):
        self.client.login(email="root@example.com", password="rootpass123")

        response = self.client.get(reverse("store:dashboard_home"), follow=True)

        self.assertRedirects(response, reverse("store:warehouse_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_legacy_warehouse_path_redirects_to_stock(self):
        self.client.login(email="mod@example.com", password="modpass123")

        response = self.client.get("/dashboard/warehouse/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("store:warehouse_dashboard"))


class WarehouseStockManagementTest(TestCase):
    """Тесты управления остатками на складе."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            email="mod2@example.com",
            password="modpass123",
            is_staff=True,
            is_active=True,
        )
        self.moderator.groups.add(Group.objects.create(name="Модераторы"))
        self.regular_user = User.objects.create_user(
            email="regular@example.com",
            password="regularpass123",
            is_active=True,
        )
        self.category = Category.objects.create(name="Шарфы")
        self.product = Product.objects.create(name="Шарф ФК Шинник", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("scarf.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SCARF-BLUE-001",
            size="One Size",
            color="Синий",
            price=Decimal("1990.00"),
            quantity=5,
            image=self.image,
        )

    def test_stock_update_available_for_moderator(self):
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:warehouse_variant_stock_update", kwargs={"pk": self.variant.pk}),
            data={"quantity": 12},
        )

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 12)

    def test_stock_update_forbidden_for_regular_user(self):
        self.client.login(email="regular@example.com", password="regularpass123")

        response = self.client.post(
            reverse("store:warehouse_variant_stock_update", kwargs={"pk": self.variant.pk}),
            data={"quantity": 12},
        )

        self.assertEqual(response.status_code, 403)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 5)

    def test_warehouse_page_shows_stock_summary(self):
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Склад")
        self.assertContains(response, self.product.name)
        self.assertContains(response, "Доступно: 3")
        self.assertContains(response, "Физически: 5 / Резерв: 2")

    def test_warehouse_page_searches_and_displays_real_variant_sku(self):
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_dashboard"), {"q": self.variant.sku})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.variant.sku)

    def test_warehouse_sku_search_keeps_product_level_stock_aggregates(self):
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
        ProductVariant.objects.create(
            product=self.product,
            sku="SCARF-RED-002",
            size="L",
            color="Красный",
            price=Decimal("990.00"),
            quantity=10,
            reserved_quantity=1,
        )
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_dashboard"), {"q": self.variant.sku})

        self.assertEqual(response.status_code, 200)
        products = response.context["products"]
        self.assertEqual(len(products), 1)
        product = products[0]
        self.assertEqual(product.variant_count, 2)
        self.assertEqual(product.stock_total, 15)
        self.assertEqual(product.reserved_stock_total, 3)
        self.assertEqual(product.available_stock_total, 12)
        self.assertEqual(product.min_price, Decimal("990.00"))
        self.assertEqual(product.stock_state, "in")

    def test_product_manage_page_shows_variant_stock_breakdown_and_active_reserves(self):
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
        customer = User.objects.create_user(email="stock-customer@example.com", password="customerpass123")
        order = Order.objects.create(
            number="ORD-STOCK-RESERVE",
            user=customer,
            recipient_name="Покупатель",
            email=customer.email,
            phone="+79001112233",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount=Decimal("3980.00"),
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.pk),
            unit_price=Decimal("1990.00"),
            quantity=2,
            line_total=Decimal("3980.00"),
        )
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Физический остаток")
        self.assertContains(response, "Резерв")
        self.assertContains(response, "Доступно к продаже")
        self.assertContains(response, "3 шт.")
        self.assertContains(response, "Активные резервы")
        self.assertContains(response, order.number)

    def test_product_manage_page_updates_main_product_form(self):
        self.client.login(email="mod2@example.com", password="modpass123")
        new_category = Category.objects.create(name="Сувениры")

        response = self.client.post(
            reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}),
            data={
                "name": "Обновленный шарф",
                "category": new_category.pk,
                "description": "Новое описание",
            },
        )

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Обновленный шарф")
        self.assertEqual(self.product.category_id, new_category.pk)
        self.assertEqual(self.product.description, "Новое описание")

    def test_warehouse_create_product_is_not_on_sale_by_default(self):
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:warehouse_product_create"),
            data={
                "name": "Новый складской товар",
                "category": self.category.pk,
                "description": "Пока без публикации",
            },
        )

        created_product = Product.objects.get(name="Новый складской товар")
        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": created_product.pk}))
        self.assertFalse(created_product.is_on_sale)

    def test_publish_product_available_for_moderator(self):
        self.client.login(email="mod2@example.com", password="modpass123")
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.post(reverse("store:warehouse_product_publish", kwargs={"pk": self.product.pk}))

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_on_sale)

    def test_unpublish_product_available_for_moderator(self):
        self.client.login(email="mod2@example.com", password="modpass123")
        self.product.is_on_sale = True
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.post(reverse("store:warehouse_product_unpublish", kwargs={"pk": self.product.pk}))

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_on_sale)

    def test_publish_product_forbidden_for_regular_user(self):
        self.client.login(email="regular@example.com", password="regularpass123")
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.post(reverse("store:warehouse_product_publish", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_on_sale)

    def test_image_set_primary_available_for_moderator(self):
        secondary_image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("scarf-secondary.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=False,
        )
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.post(reverse("store:warehouse_image_set_primary", kwargs={"pk": secondary_image.pk}))

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.image.refresh_from_db()
        secondary_image.refresh_from_db()
        self.assertFalse(self.image.is_primary)
        self.assertTrue(secondary_image.is_primary)

    def test_image_set_primary_forbidden_for_regular_user(self):
        secondary_image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("scarf-secondary.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=False,
        )
        self.client.login(email="regular@example.com", password="regularpass123")

        response = self.client.post(reverse("store:warehouse_image_set_primary", kwargs={"pk": secondary_image.pk}))

        self.assertEqual(response.status_code, 403)
        self.image.refresh_from_db()
        secondary_image.refresh_from_db()
        self.assertTrue(self.image.is_primary)
        self.assertFalse(secondary_image.is_primary)

    def test_product_manage_page_shows_set_primary_button_for_non_primary_images(self):
        ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("scarf-secondary.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=False,
        )
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сделать основным")

    def test_image_create_page_has_preview_and_replace_controls(self):
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_image_create", kwargs={"product_pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="imagePreviewContainer"', html=False)
        self.assertContains(response, 'id="replaceImageButton"', html=False)
        self.assertContains(response, 'id="clearImageButton"', html=False)
        self.assertContains(response, 'src="/static/js/dashboard-image-preview.js?v=1"', html=False)
        self.assertNotContains(response, "URL.createObjectURL(", html=False)


class DashboardOrdersManagementTest(TestCase):
    """Тесты вкладки заказов модераторского дашборда."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            email="dashboard-mod@example.com",
            password="modpass123",
            is_staff=True,
            is_active=True,
        )
        self.moderator.groups.add(Group.objects.create(name="Модераторы"))
        self.regular_user = User.objects.create_user(
            email="dashboard-user@example.com",
            password="userpass123",
            is_active=True,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="customerpass123",
            is_active=True,
        )

        self.category = Category.objects.create(name="Сувениры")
        self.product = Product.objects.create(name="Шарф ФК Шинник", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Синий",
            price=Decimal("1500.00"),
            quantity=10,
            reserved_quantity=1,
        )
        self.order = Order.objects.create(
            number="ORD-TEST-0001",
            user=self.customer,
            recipient_name="Покупатель",
            email=self.customer.email,
            phone="+79001112233",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            subtotal_amount=Decimal("1500.00"),
            delivery_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("1500.00"),
            customer_comment="Позвонить перед выдачей",
        )
        OrderItem.objects.create(
            order=self.order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.pk),
            unit_price=Decimal("1500.00"),
            quantity=1,
            line_total=Decimal("1500.00"),
        )

    def test_orders_dashboard_available_for_moderator(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.get(reverse("store:dashboard_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заказы")
        self.assertContains(response, self.order.number)
        self.assertContains(response, "Новый")

    def test_orders_dashboard_searches_by_phone_and_filters_by_payment_status(self):
        other_order = Order.objects.create(
            number="ORD-TEST-0002",
            user=self.customer,
            recipient_name="Другой покупатель",
            email="other-customer@example.com",
            phone="+79998887766",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.SUCCEEDED,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount=Decimal("2500.00"),
        )
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.get(
            reverse("store:dashboard_orders"),
            {
                "q": "1112233",
                "payment_status": Order.PaymentStatus.PENDING,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.number)
        self.assertContains(response, "+79001112233")
        self.assertNotContains(response, other_order.number)

    def test_orders_dashboard_filters_by_created_date_and_amount(self):
        other_order = Order.objects.create(
            number="ORD-TEST-0003",
            user=self.customer,
            recipient_name="Другой покупатель",
            email="other-date@example.com",
            phone="+79990000000",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount=Decimal("500.00"),
        )
        old_date = timezone.localdate() - timedelta(days=10)
        old_datetime = timezone.make_aware(datetime.combine(old_date, time(hour=12)))
        Order.objects.filter(pk=other_order.pk).update(created_at=old_datetime)
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.get(
            reverse("store:dashboard_orders"),
            {
                "created_from": timezone.localdate().isoformat(),
                "amount_min": "1000",
                "amount_max": "1600",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.number)
        self.assertNotContains(response, other_order.number)

    def test_order_detail_displays_operational_context(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.get(reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"mailto:{self.customer.email}")
        self.assertContains(response, "tel:+79001112233")
        self.assertContains(response, "Комментарий клиента")
        self.assertContains(response, "Позвонить перед выдачей")
        self.assertContains(response, "Забрать до")

    def test_guest_order_without_user_renders_dashboard_pages(self):
        guest_order = Order.objects.create(
            number="ORD-GUEST-0001",
            user=None,
            recipient_name="",
            email="guest@example.com",
            phone="+79004445566",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            subtotal_amount=Decimal("1500.00"),
            delivery_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("1500.00"),
        )
        OrderStatusTransition.log_if_changed(
            order=guest_order,
            transition_type=OrderStatusTransition.TransitionType.DASHBOARD_STATUS,
            from_value="draft",
            to_value="new",
            changed_by=None,
        )
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        list_response = self.client.get(reverse("store:dashboard_orders"))
        detail_response = self.client.get(reverse("store:dashboard_order_detail", kwargs={"pk": guest_order.pk}))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "guest@example.com")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "guest@example.com")
        self.assertContains(detail_response, "mailto:guest@example.com")
        self.assertContains(detail_response, "Система")

    def test_order_detail_allows_staff_note_update(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_staff_note_update", kwargs={"pk": self.order.pk}),
            data={"staff_note": "Клиент просил пакет к заказу"},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.staff_note, "Клиент просил пакет к заказу")

        detail_response = self.client.get(reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.assertContains(detail_response, "Клиент просил пакет к заказу")

    def test_order_status_update_from_dashboard_detail(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "ready"},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.RESERVED)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)

    def test_order_payment_status_update_from_dashboard_detail(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_payment_status_update", kwargs={"pk": self.order.pk}),
            data={"payment_status": Order.PaymentStatus.SUCCEEDED},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        payment = Payment.objects.get(order=self.order, provider=Payment.Provider.MANUAL)
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(self.order.paid_at)

    def test_order_cannot_be_issued_without_successful_payment(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "issued"},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.NEW)
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_order_can_be_issued_after_successful_payment(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")
        self.client.post(
            reverse("store:dashboard_order_payment_status_update", kwargs={"pk": self.order.pk}),
            data={"payment_status": Order.PaymentStatus.SUCCEEDED},
        )
        self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "ready"},
        )

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "issued"},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(self.order.issued_at)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 9)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_order_cancel_from_dashboard_uses_cancellation_service(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "cancelled"},
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertEqual(self.variant.quantity, 10)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_cancelled_order_cannot_be_reopened_from_dashboard(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")
        self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "cancelled"},
        )

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "new"},
            follow=True,
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertContains(response, "Нельзя изменить заказ после отмены или выдачи.")

    def test_delivered_order_cannot_move_back_to_processing_from_dashboard(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")
        self.client.post(
            reverse("store:dashboard_order_payment_status_update", kwargs={"pk": self.order.pk}),
            data={"payment_status": Order.PaymentStatus.SUCCEEDED},
        )
        self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "ready"},
        )
        self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "issued"},
        )

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "processing"},
            follow=True,
        )

        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)
        self.assertContains(response, "Нельзя изменить заказ после отмены или выдачи.")

    def test_order_detail_displays_status_transition_history(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")

        response = self.client.post(
            reverse("store:dashboard_order_status_update", kwargs={"pk": self.order.pk}),
            data={"status": "processing"},
        )
        self.assertRedirects(response, reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))

        self.assertTrue(
            OrderStatusTransition.objects.filter(
                order=self.order,
                transition_type=OrderStatusTransition.TransitionType.DASHBOARD_STATUS,
                from_value="new",
                to_value="processing",
            ).exists()
        )
        detail_response = self.client.get(reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}))
        self.assertContains(detail_response, "История изменений")
        self.assertContains(detail_response, "Статус dashboard")
        self.assertContains(detail_response, "new")
        self.assertContains(detail_response, "processing")
        self.assertContains(detail_response, self.moderator.email)

    def test_orders_dashboard_forbidden_for_regular_user(self):
        self.client.login(email="dashboard-user@example.com", password="userpass123")

        response = self.client.get(reverse("store:dashboard_orders"))

        self.assertEqual(response.status_code, 403)


class ModeratorGroupCommandTest(TestCase):
    """Тесты команды создания/обновления группы модераторов."""

    def test_command_updates_existing_group_with_orders_and_payments_permissions(self):
        group = Group.objects.create(name="Модераторы")

        call_command("create_moderator_group")

        group.refresh_from_db()
        group_permissions = set(group.permissions.values_list("codename", flat=True))
        expected_permissions = {
            "view_product",
            "add_product",
            "change_product",
            "delete_product",
            "view_category",
            "add_category",
            "change_category",
            "delete_category",
            "view_order",
            "change_order",
            "view_orderitem",
            "view_payment",
            "add_payment",
            "change_payment",
        }
        self.assertTrue(expected_permissions.issubset(group_permissions))


class OldCatalogCrudRoutesRemovedTest(TestCase):
    """Старые CRUD endpoints витрины заменены dashboard-flow."""

    def test_old_product_and_category_crud_routes_are_not_registered(self):
        removed_paths = [
            "/products/create/",
            "/products/1/edit/",
            "/products/1/delete/",
            "/categories/create/",
            "/categories/1/edit/",
            "/categories/1/delete/",
        ]

        for path in removed_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)


class AddToCartSaleStateTest(TestCase):
    """Тесты недоступности снятых с продажи товаров в корзине."""

    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Аксессуары")
        self.product = Product.objects.create(name="Тестовый шарф", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Красный",
            price=Decimal("1999.99"),
            quantity=10,
        )

    def test_add_to_cart_rejects_product_not_on_sale(self):
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.post(
            reverse("store:add_to_cart"),
            {"variant_id": self.variant.id, "quantity": 1},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {
                "success": False,
                "error": "Товар снят с продажи и недоступен для заказа.",
            },
        )
        self.assertFalse(CartItem.objects.filter(product_variant=self.variant).exists())


class RemoveFromCartViewTest(TestCase):
    """Тесты для RemoveFromCartViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.category = Category.objects.create(name="Аксессуары")
        self.product = Product.objects.create(name="Тестовый шарф", category=self.category)
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image, is_primary=True)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Красный",
            price=Decimal("1999.99"),
            quantity=10,
            image=self.image,
        )

    def test_remove_from_cart_deletes_item_and_returns_summary(self):
        """Проверяет сценарий 'remove from cart deletes item and returns summary'."""
        session = self.client.session
        session.save()
        cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=2)

        response = self.client.post(reverse("store:remove_from_cart"), {"variant_id": self.variant.id})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CartItem.objects.filter(cart=cart, product_variant=self.variant).exists())
        self.assertJSONEqual(
            response.content,
            {
                "success": True,
                "message": "Товар удален из корзины",
                "cart_total": 0.0,
                "cart_items": 0,
            },
        )

    def test_remove_from_cart_returns_404_when_item_is_missing(self):
        """Проверяет сценарий 'remove from cart returns 404 when item is missing'."""
        response = self.client.post(reverse("store:remove_from_cart"), {"variant_id": self.variant.id})

        self.assertEqual(response.status_code, 404)
        self.assertJSONEqual(response.content, {"success": False, "error": "Товар не найден в корзине"})


class CartPageRenderingTest(TestCase):
    """Тесты рендера страницы корзины."""

    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Аксессуары")
        self.product = Product.objects.create(name="Тестовый шарф", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size=None,
            color="Сине-гранатовый",
            price=Decimal("1999.99"),
            quantity=10,
        )

        session = self.client.session
        session.save()
        cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=1)

    def test_cart_page_hides_none_variant_values_and_positions_block(self):
        response = self.client.get(reverse("store:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сине-гранатовый")
        self.assertNotContains(response, "None /")
        self.assertNotContains(response, "позиций в корзине")

    def test_cart_page_shows_unavailable_status_for_product_not_on_sale(self):
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.get(reverse("store:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Товар снят с продажи")
        self.assertNotContains(
            response,
            reverse("store:product_detail", kwargs={"pk": self.product.pk}),
        )

    def test_cart_page_shows_unavailable_status_for_out_of_stock_product(self):
        self.variant.quantity = 0
        self.variant.save(update_fields=["quantity"])

        response = self.client.get(reverse("store:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Данный товар закончился")
        self.assertNotContains(
            response,
            reverse("store:product_detail", kwargs={"pk": self.product.pk}),
        )


class CartServiceItemsDetailsTest(TestCase):
    """Регрессия: позиции корзины не должны дублироваться в сервисе."""

    def setUp(self):
        self.category = Category.objects.create(name="Форма")
        self.product = Product.objects.create(name="Домашняя футболка", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("3499.00"),
            quantity=7,
        )
        self.cart = Cart.objects.create(session_key="details-session")
        CartItem.objects.create(cart=self.cart, product_variant=self.variant, quantity=2)
        self.cart_service = CartService()

    def test_get_cart_items_with_details_returns_single_row_per_cart_item(self):
        items = self.cart_service.get_cart_items_with_details(self.cart)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["variant_id"], self.variant.id)
        self.assertEqual(items[0]["max_quantity"], self.variant.available_quantity)
        self.assertEqual(items[0]["availability_message"], "")


class CartServiceValidationTest(TestCase):
    """Тесты общей валидации количества в CartService."""

    def setUp(self):
        self.category = Category.objects.create(name="Валидация корзины")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Черный",
            price=Decimal("2500.00"),
            quantity=2,
        )
        self.cart = Cart.objects.create(session_key="cart-validation-session")
        self.cart_context = CartContext(
            cart=self.cart,
            user_id=None,
            session_key=self.cart.session_key,
            is_authenticated=False,
        )
        self.cart_service = CartService()

    def test_add_item_preserves_insufficient_stock_error_message(self):
        with self.assertRaises(InsufficientStockError) as context:
            self.cart_service.add_item(self.cart_context, self.variant.pk, quantity=3)

        self.assertEqual(str(context.exception), "Недостаточно товара на складе. Доступно: 2")
        self.assertEqual(context.exception.available_quantity, 2)
        self.assertFalse(CartItem.objects.filter(cart=self.cart).exists())

    def test_add_item_validates_combined_quantity_for_existing_cart_item(self):
        CartItem.objects.create(cart=self.cart, product_variant=self.variant, quantity=1)

        with self.assertRaises(InsufficientStockError) as context:
            self.cart_service.add_item(self.cart_context, self.variant.pk, quantity=2)

        self.assertEqual(str(context.exception), "Недостаточно товара на складе. Доступно: 2")
        self.assertEqual(self.cart.items.get(product_variant=self.variant).quantity, 1)

    def test_update_item_quantity_preserves_positive_quantity_error(self):
        with self.assertRaises(ValueError) as context:
            self.cart_service.update_item_quantity(self.cart_context, self.variant.pk, quantity=0)

        self.assertEqual(str(context.exception), "Количество должно быть больше 0")

    def test_update_item_quantity_rejects_product_not_on_sale(self):
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale"])

        with self.assertRaises(ProductNotOnSaleError) as context:
            self.cart_service.update_item_quantity(self.cart_context, self.variant.pk, quantity=1)

        self.assertEqual(str(context.exception), "Товар снят с продажи и недоступен для заказа.")


class LegalPagesCartCounterTest(TestCase):
    """Тесты отображения количества товаров в корзине на legal-страницах."""

    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Юридический мерч")
        self.product = Product.objects.create(name="Тестовый шарф", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Синий",
            price=Decimal("999.99"),
            quantity=10,
        )

        session = self.client.session
        session.save()
        cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=3)
        for slug, title in (
            ("privacy-policy", "Политика конфиденциальности"),
            ("terms-of-service", "Пользовательское соглашение"),
            ("return-policy", "Условия возврата"),
            ("offer", "Договор оферты"),
        ):
            Page.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "lead": "Тестовая юридическая страница",
                    "content": "<p>Тестовое содержание</p>",
                    "is_published": True,
                },
            )

    def test_legal_pages_use_actual_cart_counter(self):
        legal_routes = [
            "store:privacy_policy",
            "store:terms_of_service",
            "store:return_policy",
            "store:offer",
        ]

        for route_name in legal_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertIn("cart_count", response.context)
                self.assertEqual(response.context["cart_count"], 3)


class WarehouseImageDeleteDetachVariantTest(TestCase):
    """Тесты безопасного удаления изображения, привязанного к варианту."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            email="mod-image@example.com",
            password="modpass123",
            is_staff=True,
            is_active=True,
        )
        self.moderator.groups.add(Group.objects.create(name="Модераторы"))
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("image.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="L",
            color="Красный",
            price=Decimal("2999.99"),
            quantity=5,
            image=self.image,
        )

    def test_delete_image_sets_variant_image_to_null(self):
        self.client.login(email="mod-image@example.com", password="modpass123")

        response = self.client.post(reverse("store:warehouse_image_delete", kwargs={"pk": self.image.pk}))

        self.assertRedirects(response, reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk}))
        self.assertFalse(ProductImage.objects.filter(pk=self.image.pk).exists())
        self.variant.refresh_from_db()
        self.assertIsNone(self.variant.image)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())


class CartMergeOnLoginSignalTest(TestCase):
    """Тесты объединения корзин через login signal."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="merge-user@example.com",
            password="mergepass123",
            is_active=True,
        )
        category = Category.objects.create(name="Мерч")
        product = Product.objects.create(name="Шарф тестовый", category=category)
        image = ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile("merge.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            size="One Size",
            color="Синий",
            price=Decimal("1200.00"),
            quantity=5,
            image=image,
        )

    def test_login_signal_merges_session_cart_into_user_cart(self):
        """При логине сессионная корзина должна сливаться в корзину пользователя."""
        session = self.client.session
        session.save()
        session_cart = Cart.objects.create(session_key=session.session_key)
        CartItem.objects.create(cart=session_cart, product_variant=self.variant, quantity=4)

        user_cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=user_cart, product_variant=self.variant, quantity=2)

        response = self.client.post(
            reverse("users:login"),
            data={"username": "merge-user@example.com", "password": "mergepass123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Cart.objects.filter(pk=session_cart.pk).exists())
        merged_item = CartItem.objects.get(cart=user_cart, product_variant=self.variant)
        self.assertEqual(merged_item.quantity, 5)


@skipUnlessDBFeature("has_select_for_update")
class CartMergeConcurrencyTest(TransactionTestCase):
    """Тесты конкурентного объединения корзин."""

    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(
            email="merge-parallel@example.com",
            password="mergepass123",
            is_active=True,
        )
        category = Category.objects.create(name="Параллельный мерч")
        product = Product.objects.create(name="Параллельный шарф", category=category)
        image = ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile("parallel-merge.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            size="One Size",
            color="Синий",
            price=Decimal("1200.00"),
            quantity=5,
            image=image,
        )
        self.user_cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=self.user_cart, product_variant=self.variant, quantity=2)
        self.session_cart = Cart.objects.create(session_key="parallel-session")
        CartItem.objects.create(cart=self.session_cart, product_variant=self.variant, quantity=4)

    @staticmethod
    def _merge_once(user_cart_id, session_key):
        close_old_connections()
        try:
            user_cart = Cart.objects.get(pk=user_cart_id)
            CartContextResolver().merge_session_cart_into_user_cart(user_cart, session_key)
            return "ok"
        except Exception as exc:
            return f"error:{exc}"
        finally:
            close_old_connections()

    def test_parallel_merge_same_session_cart_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self._merge_once(self.user_cart.pk, "parallel-session"),
                    range(2),
                )
            )

        self.assertEqual(results, ["ok", "ok"])
        self.assertFalse(Cart.objects.filter(pk=self.session_cart.pk).exists())
        self.assertEqual(CartItem.objects.filter(cart=self.user_cart, product_variant=self.variant).count(), 1)
        merged_item = CartItem.objects.get(cart=self.user_cart, product_variant=self.variant)
        self.assertEqual(merged_item.quantity, 5)
