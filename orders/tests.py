from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, TransactionTestCase
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import close_old_connections
from django.urls import reverse
from django.utils import timezone

from orders.forms import CheckoutForm
from orders.models import Order, OrderItem
from orders.services import CheckoutService, OrderCancellationError, OrderCancellationService
from payments.models import Payment
from store.models import Cart, CartItem, Category, Product, ProductImage, ProductVariant
from users.models import User


class CheckoutFormValidationTest(SimpleTestCase):
    """Тесты нормализации и базовой валидации checkout-формы."""

    def test_normalizes_recipient_name_and_phone(self):
        form = CheckoutForm(
            data={
                "recipient_name": "   Иван     Иванов   ",
                "email": "  buyer@example.com   ",
                "phone": " +7 (999)   000-11-22 ",
                "customer_comment": "  Подготовьте    к  вечеру  ",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient_name"], "Иван Иванов")
        self.assertEqual(form.cleaned_data["phone"], "+79990001122")

    def test_rejects_obvious_garbage_recipient_name(self):
        form = CheckoutForm(
            data={
                "recipient_name": "!!!!!",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("recipient_name", form.errors)

    def test_rejects_invalid_phone(self):
        form = CheckoutForm(
            data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "телефон не указан",
                "customer_comment": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)


class CheckoutFlowTest(TestCase):
    """Тесты MVP checkout flow."""

    def setUp(self):
        """Подготовить пользователя, товар и корзину."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="buyer@example.com",
            password="testpass123",
            first_name="Иван",
            last_name="Иванов",
            phone="+79990001122",
            is_active=True,
            is_email_confirmed=True,
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
        self.cart = Cart.objects.create(user=self.user)
        self.cart_item = CartItem.objects.create(cart=self.cart, product_variant=self.variant, quantity=2)

    def _build_service_request(self, user=None):
        request = self.factory.post(reverse("orders:checkout"))
        request.user = user or self.user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        return request

    def test_checkout_requires_authentication(self):
        """Гость должен быть перенаправлен на логин."""
        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_checkout_requires_authentication_shows_login_hint_message(self):
        response = self.client.get(reverse("orders:checkout"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Чтобы оформить заказ, войдите в аккаунт или зарегистрируйтесь.")
        self.assertContains(response, "Авторизация")

    def test_checkout_creates_order_deducts_stock_and_clears_cart(self):
        """Оформление заказа должно создать order, payment и очистить корзину."""
        self.client.login(email="buyer@example.com", password="testpass123")

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "Подготовьте к вечеру",
            },
        )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("orders:checkout_success", kwargs={"pk": order.pk}))

        self.variant.refresh_from_db()
        self.cart.refresh_from_db()

        self.assertEqual(order.delivery_method, Order.DeliveryMethod.PICKUP)
        self.assertIsNone(order.delivery_address)
        self.assertEqual(order.pickup_point_code, "main-store")
        self.assertEqual(order.recipient_name, "Иван Иванов")
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.total_amount, Decimal("3980.00"))
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.cart.items.count(), 0)

        order_item = OrderItem.objects.get(order=order)
        self.assertEqual(order_item.product_name_snapshot, "Шарф ФК Шинник")
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.line_total, Decimal("3980.00"))

        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.provider, Payment.Provider.MANUAL)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, Decimal("3980.00"))

    def test_checkout_redirects_to_profile_when_email_not_confirmed(self):
        self.user.is_email_confirmed = False
        self.user.save(update_fields=["is_email_confirmed"])
        self.client.login(email="buyer@example.com", password="testpass123")

        response = self.client.get(reverse("orders:checkout"), follow=True)

        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": self.user.pk}))
        self.assertContains(response, "Подтвердите email в личном кабинете перед оформлением заказа.")

    def test_checkout_repeat_submit_with_same_token_redirects_to_existing_order(self):
        """Повторный POST с тем же checkout_token не должен создавать новый заказ."""
        self.client.login(email="buyer@example.com", password="testpass123")
        checkout_url = reverse("orders:checkout")

        page_response = self.client.get(checkout_url)
        self.assertEqual(page_response.status_code, 200)
        checkout_token = self.client.session.get("_checkout_token")
        self.assertTrue(checkout_token)

        payload = {
            "recipient_name": "Иван Иванов",
            "email": "buyer@example.com",
            "phone": "+79990001122",
            "customer_comment": "",
            "checkout_token": checkout_token,
        }

        first_response = self.client.post(checkout_url, data=payload)
        order = Order.objects.get(user=self.user)
        success_url = reverse("orders:checkout_success", kwargs={"pk": order.pk})
        self.assertRedirects(first_response, success_url)

        second_response = self.client.post(checkout_url, data=payload)
        self.assertRedirects(second_response, success_url)

        self.variant.refresh_from_db()
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.cart.items.count(), 0)

    def test_checkout_fails_when_stock_is_insufficient(self):
        """Если товара не хватает, заказ не должен создаваться."""
        self.client.login(email="buyer@example.com", password="testpass123")
        self.variant.quantity = 1
        self.variant.save(update_fields=["quantity"])

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
        )

        self.variant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Недостаточно товара")
        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.assertEqual(self.variant.quantity, 1)
        self.assertEqual(self.cart.items.count(), 1)

    def test_checkout_service_is_idempotent_with_same_token(self):
        """Повторный checkout с тем же токеном должен вернуть уже созданный заказ."""
        service = CheckoutService()
        request = self._build_service_request()
        cleaned_data = {
            "recipient_name": "Иван Иванов",
            "email": "buyer@example.com",
            "phone": "+79990001122",
            "customer_comment": "",
        }

        first_order = service.create_order_from_cart(request, cleaned_data, checkout_token="same-token")
        second_order = service.create_order_from_cart(request, cleaned_data, checkout_token="same-token")

        self.assertEqual(first_order.pk, second_order.pk)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Payment.objects.filter(order=first_order).count(), 1)

    def test_checkout_with_nullable_variant_attributes_saves_empty_snapshots(self):
        """Checkout должен проходить при variant.size/color=None."""
        self.variant.size = None
        self.variant.color = None
        self.variant.save(update_fields=["size", "color"])

        self.client.login(email="buyer@example.com", password="testpass123")
        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
        )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("orders:checkout_success", kwargs={"pk": order.pk}))
        order_item = OrderItem.objects.get(order=order)
        self.assertEqual(order_item.size_snapshot, "")
        self.assertEqual(order_item.color_snapshot, "")

    def test_checkout_service_does_not_conflict_between_users_with_same_token(self):
        """Одинаковый checkout_token у разных пользователей не должен конфликтовать."""
        second_user = User.objects.create_user(
            email="buyer2@example.com",
            password="testpass123",
            first_name="Сергей",
            last_name="Сергеев",
            phone="+79990002233",
            is_active=True,
        )
        second_cart = Cart.objects.create(user=second_user)
        CartItem.objects.create(cart=second_cart, product_variant=self.variant, quantity=1)
        self.variant.quantity = 10
        self.variant.save(update_fields=["quantity"])

        service = CheckoutService()
        first_request = self._build_service_request(user=self.user)
        second_request = self._build_service_request(user=second_user)

        first_order = service.create_order_from_cart(
            first_request,
            cleaned_data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
            checkout_token="shared-token",
        )
        second_order = service.create_order_from_cart(
            second_request,
            cleaned_data={
                "recipient_name": "Сергей Сергеев",
                "email": "buyer2@example.com",
                "phone": "+79990002233",
                "customer_comment": "",
            },
            checkout_token="shared-token",
        )

        self.assertNotEqual(first_order.pk, second_order.pk)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Order.objects.filter(user=second_user).count(), 1)
        self.assertTrue(
            Payment.objects.filter(order=first_order, idempotency_key=f"checkout-{self.user.id}-shared-token").exists()
        )
        self.assertTrue(
            Payment.objects.filter(order=second_order, idempotency_key=f"checkout-{second_user.id}-shared-token").exists()
        )


class OrderCancellationServiceTest(TestCase):
    """Тесты доменной отмены заказа."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cancel-buyer@example.com",
            password="testpass123",
            first_name="Петр",
            last_name="Петров",
            phone="+79995554433",
            is_active=True,
        )
        self.category = Category.objects.create(name="Футболки")
        self.product = Product.objects.create(name="Футболка ФК Локомотив", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("tshirt.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        # quantity=3 имитирует уже списанный остаток для заказа на 2 шт.
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="L",
            color="Красный",
            price=Decimal("2490.00"),
            quantity=3,
            image=self.image,
        )
        self.service = OrderCancellationService()

    def _create_order_with_item(self, **order_overrides):
        order_defaults = {
            "number": f"ORD-CANCEL-{Order.objects.count() + 1}",
            "user": self.user,
            "recipient_name": "Петр Петров",
            "email": self.user.email,
            "phone": self.user.phone,
            "status": Order.Status.PLACED,
            "payment_status": Order.PaymentStatus.PENDING,
            "fulfillment_status": Order.FulfillmentStatus.NEW,
            "delivery_method": Order.DeliveryMethod.PICKUP,
            "pickup_point_code": "main-store",
            "subtotal_amount": Decimal("4980.00"),
            "delivery_amount": Decimal("0.00"),
            "discount_amount": Decimal("0.00"),
            "total_amount": Decimal("4980.00"),
            "confirmed_at": timezone.now(),
        }
        order_defaults.update(order_overrides)
        order = Order.objects.create(**order_defaults)
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("4980.00"),
        )
        return order

    def test_cancel_order_returns_stock_and_updates_statuses(self):
        order = self._create_order_with_item()
        second_variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Белый",
            price=Decimal("2490.00"),
            quantity=4,
            image=self.image,
        )
        OrderItem.objects.create(
            order=order,
            product_variant=second_variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(second_variant.id),
            size_snapshot=second_variant.size,
            color_snapshot=second_variant.color,
            unit_price=second_variant.price,
            quantity=1,
            line_total=Decimal("2490.00"),
        )

        self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        second_variant.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(second_variant.quantity, 5)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_repeated_cancellation_does_not_duplicate_stock_return(self):
        order = self._create_order_with_item()

        self.service.cancel_order(order_id=order.id, user_id=self.user.id)
        self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.items.count(), 1)

    def test_cannot_cancel_order_in_non_cancellable_status(self):
        order = self._create_order_with_item(
            status=Order.Status.SHIPPED,
            fulfillment_status=Order.FulfillmentStatus.SHIPPED,
        )

        with self.assertRaises(OrderCancellationError):
            self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.SHIPPED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertIsNone(order.cancelled_at)


class OrderConcurrencyTest(TransactionTestCase):
    """Тесты конкурентных сценариев checkout/cancel."""

    reset_sequences = True

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="parallel@example.com",
            password="testpass123",
            first_name="Иван",
            last_name="Параллельный",
            phone="+79990000001",
            is_active=True,
        )
        category = Category.objects.create(name="Параллельные тесты")
        product = Product.objects.create(name="Параллельный товар", category=category)
        image = ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile("parallel.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            size="L",
            color="Синий",
            price=Decimal("2500.00"),
            quantity=5,
            image=image,
        )
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=2)

        self.cleaned_data = {
            "recipient_name": "Иван Параллельный",
            "email": self.user.email,
            "phone": "+79990000001",
            "customer_comment": "",
        }

    def _build_checkout_request(self):
        request = self.factory.post(reverse("orders:checkout"))
        request.user = self.user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        return request

    def _run_checkout_once(self, checkout_token: str):
        close_old_connections()
        try:
            service = CheckoutService()
            request = self._build_checkout_request()
            order = service.create_order_from_cart(request, self.cleaned_data, checkout_token=checkout_token)
            return ("ok", order.pk)
        except Exception as exc:
            return ("error", str(exc))
        finally:
            close_old_connections()

    def _create_cancellable_order(self):
        order = Order.objects.create(
            number=f"ORD-CONC-{Order.objects.count() + 1}",
            user=self.user,
            recipient_name="Иван Параллельный",
            email=self.user.email,
            phone="+79990000001",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("5000.00"),
            total_amount=Decimal("5000.00"),
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.variant.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("5000.00"),
        )
        return order

    def _run_cancel_once(self, order_id: int):
        close_old_connections()
        try:
            service = OrderCancellationService()
            service.cancel_order(order_id=order_id, user_id=self.user.id)
            return "ok"
        except Exception as exc:
            return f"error:{exc}"
        finally:
            close_old_connections()

    def test_parallel_checkout_with_same_token_creates_single_order(self):
        """Два параллельных checkout с одним токеном должны вернуть один заказ."""
        token = "parallel-checkout-token"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self._run_checkout_once(token), range(2)))

        statuses = [status for status, _ in results]
        self.assertEqual(statuses.count("error"), 0, results)

        order_ids = {order_id for status, order_id in results if status == "ok"}
        self.assertEqual(len(order_ids), 1)
        order = Order.objects.get(pk=order_ids.pop())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    def test_parallel_cancellation_returns_stock_only_once(self):
        """Параллельная отмена одного заказа должна быть идемпотентной."""
        # Имитируем заказ, который уже списал 2 единицы товара.
        self.variant.quantity = 3
        self.variant.save(update_fields=["quantity"])
        order = self._create_cancellable_order()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self._run_cancel_once(order.id), range(2)))

        self.assertTrue(all(result == "ok" for result in results), results)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(self.variant.quantity, 5)
