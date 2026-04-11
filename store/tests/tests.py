from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from users.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group

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
                product=product, size="L", color="Красный", price=Decimal("2999.99"), quantity=10, image=image
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

    def test_product_list_shows_out_of_stock_status(self):
        """Товар без остатков должен маркироваться как отсутствующий."""
        visible_product = Product.objects.order_by("-created_at").first()
        visible_product.variants.update(quantity=0)

        response = self.client.get(reverse("store:product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нет в наличии")


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
        self.superuser = User.objects.create_superuser(email="root@example.com", password="rootpass123")
        self.moderator = User.objects.create_user(email="mod@example.com", password="modpass123", is_active=True)
        self.moderator.groups.add(Group.objects.create(name="moderators"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 302)

    def test_dashboard_forbidden_for_regular_user(self):
        self.client.login(email="user@example.com", password="testpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_available_for_group_moderator(self):
        self.client.login(email="mod@example.com", password="modpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дашборд модератора")

    def test_dashboard_available_for_superuser(self):
        self.client.login(email="root@example.com", password="rootpass123")

        response = self.client.get(reverse("store:dashboard_home"))

        self.assertEqual(response.status_code, 200)


class WarehouseStockManagementTest(TestCase):
    """Тесты управления остатками на складе."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(email="mod2@example.com", password="modpass123", is_active=True)
        self.moderator.groups.add(Group.objects.create(name="Модераторы"))
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

    def test_warehouse_page_shows_stock_summary(self):
        self.client.login(email="mod2@example.com", password="modpass123")

        response = self.client.get(reverse("store:warehouse_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Склад")
        self.assertContains(response, self.product.name)


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

        response = self.client.post(reverse("main_page:remove_from_cart"), {"variant_id": self.variant.id})

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
        response = self.client.post(reverse("main_page:remove_from_cart"), {"variant_id": self.variant.id})

        self.assertEqual(response.status_code, 404)
        self.assertJSONEqual(response.content, {"success": False, "error": "Товар не найден в корзине"})


class WarehouseImageDeleteDetachVariantTest(TestCase):
    """Тесты безопасного удаления изображения, привязанного к варианту."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(email="mod-image@example.com", password="modpass123", is_active=True)
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
