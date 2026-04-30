from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from users.models import User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group

from orders.models import Order, OrderItem, OrderStatusTransition
from payments.models import Payment
from store.models import Cart, CartItem, Category, Product, ProductVariant, ProductImage


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
            name="Футболка Manchester United",
            description="Официальная футболка домашнего комплекта",
            category=self.category,
        )

    def test_product_creation(self):
        """Проверяет сценарий 'product creation'."""
        self.assertEqual(self.product.name, "Футболка Manchester United")
        self.assertEqual(self.product.category, self.category)
        self.assertTrue(self.product.is_on_sale)
        self.assertTrue(self.product.created_at)
        self.assertTrue(self.product.updated_at)

    def test_product_str_method(self):
        """Проверяет сценарий 'product str method'."""
        self.assertEqual(str(self.product), "Футболка Manchester United")

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
            product=self.product, size="L", color="Красный", price=Decimal("2999.99"), quantity=10, image=self.image
        )

    def test_product_variant_creation(self):
        """Проверяет сценарий 'product variant creation'."""
        self.assertEqual(self.variant.product, self.product)
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

    def test_product_variant_price_validator(self):
        # Проверяем, что отрицательная цена не проходит валидацию при full_clean
        """Проверяет сценарий 'product variant price validator'."""
        from django.core.exceptions import ValidationError

        variant = ProductVariant(
            product=self.product, size="M", color="Синий", price=Decimal("-100"), quantity=5, image=self.image
        )
        with self.assertRaises(ValidationError):
            variant.full_clean()


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
        lower_priced_index = next(index for index, product in enumerate(products) if product.pk == lower_priced_product.pk)
        conflicted_index = next(index for index, product in enumerate(products) if product.pk == conflicted_product.pk)
        self.assertLess(lower_priced_index, conflicted_index)
        self.assertEqual(next(product.display_price for product in products if product.pk == conflicted_product.pk), Decimal("1005.00"))

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

    def test_product_detail_view_404_when_product_not_on_sale(self):
        """Снятый с продажи товар не должен открываться на витрине."""
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 404)


class ProductUpdateViewTest(TestCase):
    """Тесты для ProductUpdateViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.user = User.objects.create_user(email="testuser@example.com", password="testpass123", is_active=True)
        self.staff_user = User.objects.create_user(
            email="staffuser@example.com", password="staffpass123", is_staff=True, is_active=True
        )
        # Создаем группу "Модераторы" и добавляем staff пользователя
        from django.contrib.auth.models import Group

        moderator_group, created = Group.objects.get_or_create(name="Модераторы")
        self.staff_user.groups.add(moderator_group)
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(
            name="Тестовая футболка", description="Описание товара", category=self.category
        )

    def test_product_update_view_requires_staff(self):
        """Проверяет сценарий 'product update view requires staff'."""
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_product_update_view_denied_for_regular_user(self):
        """Проверяет сценарий 'product update view denied for regular user'."""
        self.client.login(email="testuser@example.com", password="testpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 403)

    def test_product_update_view_allowed_for_staff(self):
        """Проверяет сценарий 'product update view allowed for staff'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_update_view_template(self):
        """Проверяет сценарий 'product update view template'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_update.html")

    def test_product_update_form_submission(self):
        """Проверяет сценарий 'product update form submission'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.post(
            reverse("store:product_edit", kwargs={"pk": self.product.pk}),
            {"name": "Обновленная футболка", "description": "Обновленное описание", "category": self.category.pk},
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Обновленная футболка")
        self.assertEqual(response.status_code, 302)


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
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Склад")
        self.assertContains(response, self.product.name)

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

    def test_order_cancel_from_dashboard_uses_cancellation_service(self):
        self.client.login(email="dashboard-mod@example.com", password="modpass123")
        self.variant.quantity = 9
        self.variant.save(update_fields=["quantity", "updated_at"])

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


class ProductDeleteViewTest(TestCase):
    """Тесты для ProductDeleteViewTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.user = User.objects.create_user(email="testuser@example.com", password="testpass123", is_active=True)
        self.staff_user = User.objects.create_user(
            email="staffuser@example.com", password="staffpass123", is_staff=True, is_active=True
        )
        # Создаем группу "Модераторы" и добавляем staff пользователя
        from django.contrib.auth.models import Group

        moderator_group, created = Group.objects.get_or_create(name="Модераторы")
        self.staff_user.groups.add(moderator_group)
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(
            name="Тестовая футболка", description="Описание товара", category=self.category
        )

    def test_product_delete_view_requires_staff(self):
        """Проверяет сценарий 'product delete view requires staff'."""
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_product_delete_view_denied_for_regular_user(self):
        """Проверяет сценарий 'product delete view denied for regular user'."""
        self.client.login(email="testuser@example.com", password="testpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 403)

    def test_product_delete_view_allowed_for_staff(self):
        """Проверяет сценарий 'product delete view allowed for staff'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_delete_view_template(self):
        """Проверяет сценарий 'product delete view template'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_delete.html")

    def test_product_delete_confirmation(self):
        """Проверяет сценарий 'product delete confirmation'."""
        self.client.login(email="staffuser@example.com", password="staffpass123")
        initial_count = Product.objects.count()
        response = self.client.post(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(Product.objects.count(), initial_count - 1)
        self.assertEqual(response.status_code, 302)


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
        self.assertContains(response, "Данный товар закончился")
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
