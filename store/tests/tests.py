from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from users.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from store.models import Cart, CartItem, Category, Product, ProductVariant, ProductImage


class CategoryModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Одежда", description="Одежда для спорта")

    def test_category_creation(self):
        self.assertEqual(self.category.name, "Одежда")
        self.assertEqual(self.category.description, "Одежда для спорта")
        self.assertTrue(self.category.created_at)
        self.assertTrue(self.category.updated_at)

    def test_category_str_method(self):
        self.assertEqual(str(self.category), "Одежда")

    def test_category_unique_name(self):
        with self.assertRaises(Exception):
            Category.objects.create(name="Одежда")


class ProductModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Футболки", description="Спортивные футболки")
        self.product = Product.objects.create(
            name="Футболка Manchester United",
            description="Официальная футболка домашнего комплекта",
            category=self.category,
        )

    def test_product_creation(self):
        self.assertEqual(self.product.name, "Футболка Manchester United")
        self.assertEqual(self.product.category, self.category)
        self.assertTrue(self.product.created_at)
        self.assertTrue(self.product.updated_at)

    def test_product_str_method(self):
        self.assertEqual(str(self.product), "Футболка Manchester United")

    def test_product_without_category(self):
        product_no_category = Product.objects.create(name="Футболка без категории", description="Тестовый товар")
        self.assertIsNone(product_no_category.category)


class ProductImageModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(
            product=self.product, image=test_image, alt_text="Тестовое изображение", is_primary=True
        )

    def test_product_image_creation(self):
        self.assertEqual(self.image.product, self.product)
        self.assertEqual(self.image.alt_text, "Тестовое изображение")
        self.assertTrue(self.image.is_primary)

    def test_product_image_str_method(self):
        expected = "Изображение для Тестовая футболка"
        self.assertEqual(str(self.image), expected)


class ProductVariantModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Тестовая футболка", category=self.category)
        # Создаем тестовое изображение
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image)
        self.variant = ProductVariant.objects.create(
            product=self.product, size="L", color="Красный", price=Decimal("2999.99"), quantity=10, image=self.image
        )

    def test_product_variant_creation(self):
        self.assertEqual(self.variant.product, self.product)
        self.assertEqual(self.variant.size, "L")
        self.assertEqual(self.variant.color, "Красный")
        self.assertEqual(self.variant.price, Decimal("2999.99"))
        self.assertEqual(self.variant.quantity, 10)
        self.assertEqual(self.variant.image, self.image)

    def test_product_variant_str_method(self):
        expected = "Тестовая футболка (L, Красный)"
        self.assertEqual(str(self.variant), expected)

    def test_product_variant_unique_constraint(self):
        with self.assertRaises(Exception):
            ProductVariant.objects.create(
                product=self.product, size="L", color="Красный", price=Decimal("1999.99"), quantity=5, image=self.image
            )

    def test_product_variant_price_validator(self):
        # Проверяем, что отрицательная цена не проходит валидацию при full_clean
        from django.core.exceptions import ValidationError

        variant = ProductVariant(
            product=self.product, size="M", color="Синий", price=Decimal("-100"), quantity=5, image=self.image
        )
        with self.assertRaises(ValidationError):
            variant.full_clean()


class MainViewTest(TestCase):
    def setUp(self):
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
        response = self.client.get(reverse("store:base"))
        self.assertEqual(response.status_code, 200)

    def test_main_view_template(self):
        response = self.client.get(reverse("store:base"))
        self.assertTemplateUsed(response, "main_page/index.html")

    def test_main_view_context(self):
        response = self.client.get(reverse("store:base"))
        self.assertIn("categories", response.context)
        self.assertIn("popular_products", response.context)
        self.assertEqual(len(response.context["categories"]), 1)
        self.assertEqual(len(response.context["popular_products"]), 1)


class ProductListViewTest(TestCase):
    def setUp(self):
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
        response = self.client.get(reverse("store:product_list"))
        self.assertEqual(response.status_code, 200)

    def test_product_list_view_template(self):
        response = self.client.get(reverse("store:product_list"))
        self.assertTemplateUsed(response, "main_page/product_list.html")

    def test_product_list_view_context(self):
        response = self.client.get(reverse("store:product_list"))
        self.assertIn("products", response.context)
        self.assertIn("categories", response.context)
        self.assertEqual(len(response.context["products"]), 12)  # paginate_by = 12

    def test_product_list_pagination(self):
        response = self.client.get(reverse("store:product_list") + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 3)


class ProductDetailsViewTest(TestCase):
    def setUp(self):
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
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_detail_view_template(self):
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_details.html")

    def test_product_detail_view_context(self):
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": self.product.pk}))
        self.assertIn("product", response.context)
        self.assertIn("product_images", response.context)
        self.assertIn("variants", response.context)
        self.assertEqual(response.context["product"], self.product)

    def test_product_detail_view_404(self):
        response = self.client.get(reverse("store:product_detail", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)


class ProductUpdateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="testuser@example.com", password="testpass123")
        self.staff_user = User.objects.create_user(
            email="staffuser@example.com", password="staffpass123", is_staff=True
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
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_product_update_view_denied_for_regular_user(self):
        self.client.login(email="testuser@example.com", password="testpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 403)

    def test_product_update_view_allowed_for_staff(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_update_view_template(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_edit", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_update.html")

    def test_product_update_form_submission(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.post(
            reverse("store:product_edit", kwargs={"pk": self.product.pk}),
            {"name": "Обновленная футболка", "description": "Обновленное описание", "category": self.category.pk},
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Обновленная футболка")
        self.assertEqual(response.status_code, 302)


class ProductDeleteViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="testuser@example.com", password="testpass123")
        self.staff_user = User.objects.create_user(
            email="staffuser@example.com", password="staffpass123", is_staff=True
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
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_product_delete_view_denied_for_regular_user(self):
        self.client.login(email="testuser@example.com", password="testpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 403)

    def test_product_delete_view_allowed_for_staff(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(response.status_code, 200)

    def test_product_delete_view_template(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        response = self.client.get(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertTemplateUsed(response, "main_page/product_delete.html")

    def test_product_delete_confirmation(self):
        self.client.login(email="staffuser@example.com", password="staffpass123")
        initial_count = Product.objects.count()
        response = self.client.post(reverse("store:product_delete", kwargs={"pk": self.product.pk}))
        self.assertEqual(Product.objects.count(), initial_count - 1)
        self.assertEqual(response.status_code, 302)


class RemoveFromCartViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Аксессуары")
        self.product = Product.objects.create(name="Тестовый шарф", category=self.category)
        test_image = SimpleUploadedFile("test_image.jpg", b"fake_image_data", content_type="image/jpeg")
        self.image = ProductImage.objects.create(product=self.product, image=test_image, is_primary=True)
        self.variant = ProductVariant.objects.create(
            product=self.product, size="One Size", color="Красный", price=Decimal("1999.99"), quantity=10, image=self.image
        )

    def test_remove_from_cart_deletes_item_and_returns_summary(self):
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
        response = self.client.post(reverse("main_page:remove_from_cart"), {"variant_id": self.variant.id})

        self.assertEqual(response.status_code, 404)
        self.assertJSONEqual(response.content, {"success": False, "error": "Товар не найден в корзине"})
