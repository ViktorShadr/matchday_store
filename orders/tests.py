from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from io import StringIO
from threading import Event
from time import sleep
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.db import close_old_connections
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from django.urls import reverse
from django.utils import timezone

from orders.application import CheckoutContext, DashboardOrderFlowError, DashboardOrderFlowService, OrderStatusPolicy
from orders.forms import CheckoutForm
from orders.models import Order, OrderItem, OrderStatusTransition
from orders.services import (
    CheckoutError,
    CheckoutService,
    ManualPaymentUpdateService,
    OrderAutoCancellationService,
    OrderCancellationError,
    OrderCancellationService,
    OrderIssueError,
    OrderIssueService,
)
from orders.tasks import (
    NotificationDeliveryError,
    auto_cancel_expired_pickup_orders,
    send_order_notification,
    send_order_notification_sync,
    send_staff_new_order_notification,
    send_staff_new_order_notification_sync,
)
from payments.models import Payment
from store.application import CartContext, CartContextResolver
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

    def test_checkout_form_uses_account_email_when_user_is_passed(self):
        user = type("User", (), {"email": "buyer@example.com"})()
        form = CheckoutForm(
            data={
                "recipient_name": "Иван Иванов",
                "email": "other@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.fields["email"].disabled)
        self.assertEqual(form.cleaned_data["email"], "buyer@example.com")


class OrderStatusPolicyTest(SimpleTestCase):
    """Тесты доменной политики staff-статусов заказа."""

    def test_resolves_dashboard_status_key_from_order_state(self):
        order = Order(
            status=Order.Status.PROCESSING,
            fulfillment_status=Order.FulfillmentStatus.RESERVED,
            payment_status=Order.PaymentStatus.PENDING,
        )

        self.assertEqual(OrderStatusPolicy.get_status_key(order), "ready")

        order.fulfillment_status = Order.FulfillmentStatus.DELIVERED
        self.assertEqual(OrderStatusPolicy.get_status_key(order), "issued")

        order.status = Order.Status.CANCELLED
        self.assertEqual(OrderStatusPolicy.get_status_key(order), "cancelled")

    def test_transition_policy_blocks_final_status_changes(self):
        self.assertTrue(OrderStatusPolicy.can_transition("ready", "issued"))
        self.assertFalse(OrderStatusPolicy.can_transition("issued", "processing"))
        self.assertTrue(OrderStatusPolicy.is_final_status_key("issued"))
        self.assertTrue(OrderStatusPolicy.is_final_status_key("cancelled"))

    def test_apply_status_updates_order_fields(self):
        order = Order(
            status=Order.Status.PLACED,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            payment_status=Order.PaymentStatus.SUCCEEDED,
        )

        OrderStatusPolicy.apply_status(order, "issued")

        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
        self.assertIsNotNone(order.issued_at)
        self.assertIsNone(order.cancelled_at)


@override_settings(RATELIMIT_ENABLE=False)
class CheckoutFlowTest(TestCase):
    """Тесты MVP checkout flow."""

    def setUp(self):
        """Подготовить пользователя, товар и корзину."""
        self.factory = RequestFactory()
        self.cart_context_resolver = CartContextResolver()
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
        self.assertContains(response, "Войти в личный кабинет")

    def test_checkout_page_shows_commercial_pickup_terms(self):
        self.client.login(email="buyer@example.com", password="testpass123")

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Оплата производится при получении заказа.")
        self.assertContains(response, settings.STORE_PICKUP_LOCATION_NAME)
        self.assertContains(response, "Резерв хранится 3 рабочих дня.")
        self.assertNotContains(response, "После оформления пользователь должен ясно видеть итог покупки.")
        self.assertNotContains(response, "Checkout должен быть простым и не вызывать сомнений.")

    @override_settings(
        RATELIMIT_ENABLE=True,
        RATELIMIT_CHECKOUT_IP_RATE="1/m",
        RATELIMIT_CHECKOUT_USER_RATE="1/m",
    )
    def test_checkout_rate_limited(self):
        cache.clear()
        self.client.login(email="buyer@example.com", password="testpass123")
        checkout_url = reverse("orders:checkout")
        payload = {
            "recipient_name": "Иван Иванов",
            "email": "buyer@example.com",
            "phone": "+79990001122",
            "customer_comment": "",
        }

        first_response = self.client.post(checkout_url, data=payload)
        second_response = self.client.post(checkout_url, data=payload, follow=True)

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Слишком много попыток оформления заказа. Повторите чуть позже.")

    def test_checkout_creates_order_reserves_stock_and_clears_cart(self):
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
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)
        self.assertEqual(self.cart.items.count(), 0)

        order_item = OrderItem.objects.get(order=order)
        self.assertEqual(order_item.product_name_snapshot, "Шарф ФК Шинник")
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.line_total, Decimal("3980.00"))

        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.provider, Payment.Provider.MANUAL)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, Decimal("3980.00"))

    @override_settings(STOCK_RESERVE_MODE_ENABLED=False)
    def test_checkout_fails_when_stock_reserve_mode_disabled(self):
        service = CheckoutService()
        request = self._build_service_request()
        checkout_context = CheckoutContext(
            user=self.user,
            cart_context=self.cart_context_resolver.resolve_request(request),
        )

        with self.assertRaises(CheckoutError):
            service.create_order_from_cart(
                checkout_context,
                cleaned_data={
                    "recipient_name": "Иван Иванов",
                    "email": "buyer@example.com",
                    "phone": "+79990001122",
                    "customer_comment": "",
                },
            )

        self.variant.refresh_from_db()
        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(self.cart.items.count(), 1)

    def test_checkout_redirects_to_profile_when_email_not_confirmed(self):
        self.user.is_email_confirmed = False
        self.user.save(update_fields=["is_email_confirmed"])
        self.client.login(email="buyer@example.com", password="testpass123")

        response = self.client.get(reverse("orders:checkout"), follow=True)

        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": self.user.pk}))
        self.assertContains(response, "Подтвердите email в личном кабинете перед оформлением заказа.")

    def test_checkout_service_rejects_unconfirmed_email(self):
        self.user.is_email_confirmed = False
        self.user.save(update_fields=["is_email_confirmed"])
        service = CheckoutService()
        request = self._build_service_request()
        checkout_context = CheckoutContext(
            user=self.user,
            cart_context=self.cart_context_resolver.resolve_request(request),
        )

        with self.assertRaisesRegex(CheckoutError, "Подтвердите email"):
            service.create_order_from_cart(
                checkout_context,
                cleaned_data={
                    "recipient_name": "Иван Иванов",
                    "email": "buyer@example.com",
                    "phone": "+79990001122",
                    "customer_comment": "",
                },
            )

        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(self.cart.items.count(), 1)

    def test_checkout_ignores_tampered_email_and_uses_account_email(self):
        self.client.login(email="buyer@example.com", password="testpass123")

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "recipient_name": "Иван Иванов",
                "email": "other@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
        )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("orders:checkout_success", kwargs={"pk": order.pk}))
        self.assertEqual(order.email, self.user.email)

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
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)
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
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(self.cart.items.count(), 1)

    @override_settings(CHECKOUT_MAX_ACTIVE_ORDERS=3)
    def test_checkout_fails_when_active_unpaid_order_limit_reached(self):
        """Пользователь не должен создавать новые заказы сверх лимита активных неоплаченных."""
        for index in range(3):
            Order.objects.create(
                number=f"ORD-ACTIVE-{index}",
                user=self.user,
                recipient_name="Иван Иванов",
                email="buyer@example.com",
                phone="+79990001122",
                status=Order.Status.PLACED,
                payment_status=Order.PaymentStatus.PENDING,
                fulfillment_status=Order.FulfillmentStatus.NEW,
                delivery_method=Order.DeliveryMethod.PICKUP,
                subtotal_amount=Decimal("100.00"),
                delivery_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                total_amount=Decimal("100.00"),
            )

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

        self.variant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "активные неоплаченные заказы")
        self.assertEqual(Order.objects.filter(user=self.user).count(), 3)
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(self.cart.items.count(), 1)

    @override_settings(CHECKOUT_MAX_QTY_PER_SKU=1)
    def test_checkout_fails_when_sku_quantity_limit_exceeded(self):
        """Checkout должен ограничивать количество одного SKU на уровне сервиса."""
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

        self.variant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя заказать более 1 шт.")
        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(self.cart.items.count(), 1)

    def test_checkout_service_rejects_non_positive_variant_price(self):
        class FakeCartItems:
            def __init__(self, items):
                self.items = items

            def select_related(self, *args):
                return self

            def select_for_update(self):
                return self

            def order_by(self, *args):
                return self.items

        class FakeCart:
            def __init__(self, items):
                self.items = FakeCartItems(items)

        class FakeVariantRepository:
            def __init__(self, variants):
                self.variants = variants

            def get_variants_for_update(self, variant_ids):
                return [self.variants[variant_id] for variant_id in variant_ids]

        fake_product = type("FakeProduct", (), {"name": "Тестовый товар", "is_on_sale": True})()
        fake_variant = type(
            "FakeVariant",
            (),
            {
                "id": 999,
                "product": fake_product,
                "available_quantity": 1,
                "price": Decimal("0.00"),
            },
        )()
        fake_cart_item = type(
            "FakeCartItem",
            (),
            {
                "pk": 1,
                "product_variant_id": fake_variant.id,
                "quantity": 1,
            },
        )()
        service = CheckoutService(product_variant_repository=FakeVariantRepository({fake_variant.id: fake_variant}))
        checkout_context = CheckoutContext(
            user=self.user,
            cart_context=CartContext(
                cart=FakeCart([fake_cart_item]),
                user_id=self.user.id,
                session_key=None,
                is_authenticated=True,
            ),
        )

        with self.assertRaisesRegex(CheckoutError, "Некорректная цена"):
            service.create_order_from_cart(
                checkout_context,
                {
                    "recipient_name": "Иван Иванов",
                    "email": "buyer@example.com",
                    "phone": "+79990001122",
                    "customer_comment": "",
                },
            )

    def test_checkout_fails_when_product_is_not_on_sale(self):
        """Если в корзине только снятый товар, он удаляется и checkout не создается."""
        self.client.login(email="buyer@example.com", password="testpass123")
        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "В корзине не осталось доступных товаров")
        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.assertEqual(self.cart.items.count(), 0)

    def test_checkout_skips_not_on_sale_item_and_creates_order_from_available_items(self):
        self.client.login(email="buyer@example.com", password="testpass123")
        second_product = Product.objects.create(name="Шорты Jaco", category=self.category)
        second_variant = ProductVariant.objects.create(
            product=second_product,
            size="M",
            color="Синий",
            price=Decimal("3000.00"),
            quantity=4,
        )
        CartItem.objects.create(cart=self.cart, product_variant=second_variant, quantity=1)

        self.product.is_on_sale = False
        self.product.save(update_fields=["is_on_sale", "updated_at"])

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
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_amount, Decimal("3000.00"))
        self.assertEqual(order.items.first().product_variant_id, second_variant.id)

        self.variant.refresh_from_db()
        second_variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(second_variant.quantity, 4)
        self.assertEqual(second_variant.reserved_quantity, 1)
        self.assertEqual(self.cart.items.count(), 0)

    def test_checkout_skips_out_of_stock_item_and_creates_order_from_available_items(self):
        self.client.login(email="buyer@example.com", password="testpass123")
        second_product = Product.objects.create(name="Футболка гостевая", category=self.category)
        second_variant = ProductVariant.objects.create(
            product=second_product,
            size="L",
            color="Белый",
            price=Decimal("2500.00"),
            quantity=3,
        )
        CartItem.objects.create(cart=self.cart, product_variant=second_variant, quantity=2)

        self.variant.quantity = 0
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

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("orders:checkout_success", kwargs={"pk": order.pk}))
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_amount, Decimal("5000.00"))
        self.assertEqual(order.items.first().product_variant_id, second_variant.id)

        self.variant.refresh_from_db()
        second_variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 0)
        self.assertEqual(second_variant.quantity, 3)
        self.assertEqual(second_variant.reserved_quantity, 2)
        self.assertEqual(self.cart.items.count(), 0)

    @override_settings(CHECKOUT_MAX_ACTIVE_ORDERS=1)
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

        checkout_context = CheckoutContext(
            user=self.user,
            cart_context=self.cart_context_resolver.resolve_request(request),
        )
        first_order = service.create_order_from_cart(checkout_context, cleaned_data, checkout_token="same-token")
        second_order = service.create_order_from_cart(checkout_context, cleaned_data, checkout_token="same-token")

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

    def test_checkout_success_page_shows_pickup_details_and_order_items(self):
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

        success_response = self.client.get(reverse("orders:checkout_success", kwargs={"pk": order.pk}))
        self.assertEqual(success_response.status_code, 200)
        self.assertContains(success_response, "Самовывоз")
        self.assertContains(success_response, settings.STORE_PICKUP_LOCATION_NAME)
        self.assertContains(success_response, "Срок хранения резерва")
        self.assertContains(success_response, "3 рабочих дня")
        self.assertContains(success_response, "Шарф ФК Шинник")
        self.assertContains(success_response, "Ожидает оплаты")

    def test_checkout_service_does_not_conflict_between_users_with_same_token(self):
        """Одинаковый checkout_token у разных пользователей не должен конфликтовать."""
        second_user = User.objects.create_user(
            email="buyer2@example.com",
            password="testpass123",
            first_name="Сергей",
            last_name="Сергеев",
            phone="+79990002233",
            is_active=True,
            is_email_confirmed=True,
        )
        second_cart = Cart.objects.create(user=second_user)
        CartItem.objects.create(cart=second_cart, product_variant=self.variant, quantity=1)
        self.variant.quantity = 10
        self.variant.save(update_fields=["quantity"])

        service = CheckoutService()
        first_request = self._build_service_request(user=self.user)
        second_request = self._build_service_request(user=second_user)

        first_order = service.create_order_from_cart(
            CheckoutContext(
                user=self.user,
                cart_context=self.cart_context_resolver.resolve_request(first_request),
            ),
            cleaned_data={
                "recipient_name": "Иван Иванов",
                "email": "buyer@example.com",
                "phone": "+79990001122",
                "customer_comment": "",
            },
            checkout_token="shared-token",
        )
        second_order = service.create_order_from_cart(
            CheckoutContext(
                user=second_user,
                cart_context=self.cart_context_resolver.resolve_request(second_request),
            ),
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
            Payment.objects.filter(
                order=second_order, idempotency_key=f"checkout-{second_user.id}-shared-token"
            ).exists()
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 10)
        self.assertEqual(self.variant.reserved_quantity, 3)


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
        # reserved_quantity=2 имитирует резерв активного заказа на 2 шт.
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="L",
            color="Красный",
            price=Decimal("2490.00"),
            quantity=5,
            reserved_quantity=2,
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
            quantity=5,
            reserved_quantity=1,
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
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(second_variant.quantity, 5)
        self.assertEqual(second_variant.reserved_quantity, 0)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_cancel_order_cancels_manual_payment_and_keeps_order_cancelled_after_payment_save(self):
        order = self._create_order_with_item()
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.MANUAL,
            idempotency_key="cancel-manual-payment",
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            currency=order.currency,
        )

        self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)

        payment.save()
        order.refresh_from_db()

        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)

    def test_cancel_order_creates_status_transition_audit(self):
        order = self._create_order_with_item()

        self.service.cancel_order(order_id=order.id, user_id=self.user.id, actor=self.user)

        transitions = {
            transition.transition_type: transition for transition in OrderStatusTransition.objects.filter(order=order)
        }
        self.assertIn(OrderStatusTransition.TransitionType.ORDER_STATUS, transitions)
        self.assertIn(OrderStatusTransition.TransitionType.FULFILLMENT_STATUS, transitions)
        self.assertIn(OrderStatusTransition.TransitionType.PAYMENT_STATUS, transitions)
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.ORDER_STATUS].from_value,
            Order.Status.PLACED,
        )
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.ORDER_STATUS].to_value,
            Order.Status.CANCELLED,
        )
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.FULFILLMENT_STATUS].from_value,
            Order.FulfillmentStatus.NEW,
        )
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.FULFILLMENT_STATUS].to_value,
            Order.FulfillmentStatus.CANCELLED,
        )
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.PAYMENT_STATUS].from_value,
            Order.PaymentStatus.PENDING,
        )
        self.assertEqual(
            transitions[OrderStatusTransition.TransitionType.PAYMENT_STATUS].to_value,
            Order.PaymentStatus.CANCELLED,
        )
        self.assertTrue(
            all(transition.changed_by_id == self.user.id for transition in transitions.values()),
            transitions,
        )

    def test_ready_order_can_be_cancelled(self):
        order = self._create_order_with_item(
            status=Order.Status.PROCESSING,
            fulfillment_status=Order.FulfillmentStatus.RESERVED,
        )

        self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)

    def test_repeated_cancellation_does_not_duplicate_stock_return(self):
        order = self._create_order_with_item()

        self.service.cancel_order(order_id=order.id, user_id=self.user.id)
        self.service.cancel_order(order_id=order.id, user_id=self.user.id)

        self.variant.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)
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

        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.SHIPPED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertIsNone(order.cancelled_at)


class OrderIssueServiceTest(TestCase):
    """Тесты доменных guard-ов выдачи заказа."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="issue-buyer@example.com",
            password="testpass123",
            first_name="Ирина",
            last_name="Выдача",
            phone="+79990001122",
            is_active=True,
        )
        self.category = Category.objects.create(name="Шарфы")
        self.product = Product.objects.create(name="Шарф клуба", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("scarf.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Синий",
            price=Decimal("1000.00"),
            quantity=5,
            reserved_quantity=2,
            image=self.image,
        )
        self.service = OrderIssueService()

    def _create_order_with_item(
        self,
        *,
        status=Order.Status.PROCESSING,
        fulfillment_status=Order.FulfillmentStatus.RESERVED,
        payment_status=Order.PaymentStatus.SUCCEEDED,
    ):
        order = Order.objects.create(
            number=f"ORD-ISSUE-{Order.objects.count() + 1}",
            user=self.user,
            recipient_name="Ирина Выдача",
            email=self.user.email,
            phone=self.user.phone,
            status=status,
            payment_status=payment_status,
            fulfillment_status=fulfillment_status,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("2000.00"),
            delivery_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("2000.00"),
            confirmed_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("2000.00"),
        )
        return order

    def test_consume_reserved_stock_rejects_non_issuable_order_status(self):
        order = self._create_order_with_item(
            status=Order.Status.PLACED,
            fulfillment_status=Order.FulfillmentStatus.NEW,
        )

        with self.assertRaises(OrderIssueError):
            self.service.consume_reserved_stock(order_id=order.id)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)

    def test_consume_reserved_stock_rejects_order_without_successful_payment(self):
        order = self._create_order_with_item(payment_status=Order.PaymentStatus.PENDING)

        with self.assertRaises(OrderIssueError):
            self.service.consume_reserved_stock(order_id=order.id)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)

    def test_consume_reserved_stock_for_ready_paid_order(self):
        order = self._create_order_with_item()

        returned_order = self.service.consume_reserved_stock(order_id=order.id)

        self.variant.refresh_from_db()
        self.assertEqual(returned_order.id, order.id)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_consume_reserved_stock_is_idempotent_for_already_issued_order(self):
        order = self._create_order_with_item(
            status=Order.Status.DELIVERED,
            fulfillment_status=Order.FulfillmentStatus.DELIVERED,
        )
        self.variant.quantity = 3
        self.variant.reserved_quantity = 0
        self.variant.save(update_fields=["quantity", "reserved_quantity", "updated_at"])

        returned_order = self.service.consume_reserved_stock(order_id=order.id)

        self.variant.refresh_from_db()
        self.assertEqual(returned_order.id, order.id)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)


@override_settings(ORDER_PICKUP_RETENTION_BUSINESS_DAYS=3, ORDER_AUTO_CANCEL_BATCH_SIZE=100)
class OrderAutoCancellationServiceTest(TestCase):
    """Тесты автоотмены заказов самовывоза по рабочим дням."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="auto-cancel@example.com",
            password="testpass123",
            first_name="Анна",
            last_name="Автоотмена",
            phone="+79995550000",
            is_active=True,
        )
        self.category = Category.objects.create(name="Автоотмена")
        self.product = Product.objects.create(name="Товар для автоотмены", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("1000.00"),
            quantity=3,
        )
        self.service = OrderAutoCancellationService()

    @staticmethod
    def _local_datetime(year, month, day, hour=10, minute=0):
        return timezone.make_aware(datetime(year, month, day, hour, minute))

    def _create_order_with_item(self, *, placed_at, **order_overrides):
        order_defaults = {
            "number": f"ORD-AUTO-{Order.objects.count() + 1}",
            "user": self.user,
            "recipient_name": "Анна Автоотмена",
            "email": self.user.email,
            "phone": self.user.phone,
            "status": Order.Status.PLACED,
            "payment_status": Order.PaymentStatus.PENDING,
            "fulfillment_status": Order.FulfillmentStatus.NEW,
            "delivery_method": Order.DeliveryMethod.PICKUP,
            "pickup_point_code": "main-store",
            "subtotal_amount": Decimal("2000.00"),
            "delivery_amount": Decimal("0.00"),
            "discount_amount": Decimal("0.00"),
            "total_amount": Decimal("2000.00"),
            "confirmed_at": placed_at,
        }
        order_defaults.update(order_overrides)
        order = Order.objects.create(**order_defaults)
        Order.objects.filter(pk=order.pk).update(created_at=placed_at, confirmed_at=placed_at)
        order.refresh_from_db()
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("2000.00"),
        )
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
        return order

    def test_pickup_deadline_skips_weekends(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        order = self._create_order_with_item(placed_at=friday)

        deadline = self.service.get_pickup_deadline(order)

        self.assertEqual(deadline, self._local_datetime(2026, 5, 6, 10, 0))

    def test_does_not_cancel_before_three_business_days_pass(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        tuesday = self._local_datetime(2026, 5, 5, 10, 0)
        order = self._create_order_with_item(placed_at=friday)

        result = self.service.cancel_expired_pickup_orders(now=tuesday)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result["cancelled"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 2)

    def test_does_not_cancel_when_created_at_expired_but_confirmed_at_is_fresh(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        monday = self._local_datetime(2026, 5, 4, 10, 0)
        wednesday = self._local_datetime(2026, 5, 6, 10, 1)
        order = self._create_order_with_item(placed_at=friday)
        Order.objects.filter(pk=order.pk).update(created_at=friday, confirmed_at=monday)

        result = self.service.cancel_expired_pickup_orders(now=wednesday)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["cancelled"], 0)
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(self.variant.reserved_quantity, 2)

    def test_cancels_after_three_business_days_pass(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        wednesday = self._local_datetime(2026, 5, 6, 10, 1)
        order = self._create_order_with_item(placed_at=friday)

        result = self.service.cancel_expired_pickup_orders(now=wednesday)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result["cancelled"], 1)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_auto_cancel_falls_back_to_created_at_when_confirmed_at_is_missing(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        wednesday = self._local_datetime(2026, 5, 6, 10, 1)
        order = self._create_order_with_item(placed_at=friday)
        Order.objects.filter(pk=order.pk).update(confirmed_at=None)

        result = self.service.cancel_expired_pickup_orders(now=wednesday)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result["cancelled"], 1)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_does_not_cancel_paid_order(self):
        friday = self._local_datetime(2026, 5, 1, 10, 0)
        wednesday = self._local_datetime(2026, 5, 6, 10, 1)
        order = self._create_order_with_item(
            placed_at=friday,
            payment_status=Order.PaymentStatus.SUCCEEDED,
        )

        result = self.service.cancel_expired_pickup_orders(now=wednesday)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.SUCCEEDED)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 2)

    @patch("orders.services.OrderAutoCancellationService.cancel_expired_pickup_orders")
    def test_auto_cancel_expired_pickup_orders_task_delegates_to_service(self, mock_cancel_expired):
        mock_cancel_expired.return_value = {"scanned": 1, "cancelled": 1, "skipped": 0, "failed": 0}

        result = auto_cancel_expired_pickup_orders()

        self.assertEqual(result["cancelled"], 1)
        mock_cancel_expired.assert_called_once_with()


class StockReservationBackfillCommandTest(TestCase):
    """Тесты одноразовой команды backfill резервов склада."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="backfill@example.com",
            password="testpass123",
            first_name="Бэкфилл",
            last_name="Резервов",
            phone="+79990000003",
            is_active=True,
        )
        self.category = Category.objects.create(name="Backfill")
        self.product = Product.objects.create(name="Backfill товар", category=self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("1000.00"),
            quantity=3,
        )

    def _create_order_with_item(
        self,
        *,
        status=Order.Status.PLACED,
        fulfillment_status=Order.FulfillmentStatus.NEW,
        quantity=2,
    ):
        order = Order.objects.create(
            number=f"ORD-BACKFILL-{Order.objects.count() + 1}",
            user=self.user,
            recipient_name="Бэкфилл Резервов",
            email=self.user.email,
            phone=self.user.phone,
            status=status,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=fulfillment_status,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("2000.00"),
            total_amount=Decimal("2000.00"),
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=quantity,
            line_total=self.variant.price * quantity,
        )
        return order

    def test_backfill_stock_reservations_dry_run_does_not_update_stock(self):
        self._create_order_with_item()
        stdout = StringIO()

        call_command("backfill_stock_reservations", stdout=stdout)

        self.variant.refresh_from_db()
        self.assertIn("DRY-RUN", stdout.getvalue())
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_backfill_stock_reservations_refuses_apply_while_checkout_live(self):
        self._create_order_with_item()

        with self.assertRaises(CommandError):
            call_command("backfill_stock_reservations", "--apply", stdout=StringIO())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)

    @override_settings(STOCK_RESERVE_MODE_ENABLED=False)
    def test_backfill_stock_reservations_apply_is_idempotent(self):
        self._create_order_with_item(quantity=2)
        self._create_order_with_item(
            status=Order.Status.DELIVERED,
            fulfillment_status=Order.FulfillmentStatus.DELIVERED,
            quantity=1,
        )
        self._create_order_with_item(
            status=Order.Status.CANCELLED,
            fulfillment_status=Order.FulfillmentStatus.CANCELLED,
            quantity=1,
        )
        stdout = StringIO()

        call_command("backfill_stock_reservations", "--apply", stdout=stdout)

        self.variant.refresh_from_db()
        self.assertIn("APPLIED", stdout.getvalue())
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)

        call_command("backfill_stock_reservations", "--apply", stdout=StringIO())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)


class OrderConcurrencyTest(TransactionTestCase):
    """Тесты конкурентных сценариев checkout/cancel."""

    reset_sequences = True

    def setUp(self):
        self.factory = RequestFactory()
        self.cart_context_resolver = CartContextResolver()
        self.user = User.objects.create_user(
            email="parallel@example.com",
            password="testpass123",
            first_name="Иван",
            last_name="Параллельный",
            phone="+79990000001",
            is_active=True,
            is_email_confirmed=True,
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
            checkout_context = CheckoutContext(
                user=self.user,
                cart_context=self.cart_context_resolver.resolve_request(request),
            )
            order = service.create_order_from_cart(
                checkout_context,
                self.cleaned_data,
                checkout_token=checkout_token,
            )
            return ("ok", order.pk)
        except Exception as exc:
            return ("error", str(exc))
        finally:
            close_old_connections()

    def _run_checkout_for_user_once(self, user_id: int, checkout_token: str):
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            request = self._build_checkout_request()
            request.user = user
            checkout_context = CheckoutContext(
                user=user,
                cart_context=self.cart_context_resolver.resolve_request(request),
            )
            order = CheckoutService().create_order_from_cart(
                checkout_context,
                {
                    "recipient_name": user.email,
                    "email": user.email,
                    "phone": "+79990000001",
                    "customer_comment": "",
                },
                checkout_token=checkout_token,
            )
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
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
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

    def _run_dashboard_status_once(self, order_id: int, next_status: str):
        close_old_connections()
        try:
            service = DashboardOrderFlowService(
                cancellation_service=OrderCancellationService(),
                payment_service=ManualPaymentUpdateService(),
            )
            order = Order.objects.get(pk=order_id)
            result = service.update_order_status(order, next_status)
            return ("ok", next_status, result.message)
        except Exception as exc:
            return ("error", next_status, str(exc))
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
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_checkout_load_smoke_preserves_stock_invariants(self):
        """N параллельных checkout не должны перепродавать SKU с малым остатком."""
        self.variant.quantity = 3
        self.variant.reserved_quantity = 0
        self.variant.save(update_fields=["quantity", "reserved_quantity", "updated_at"])

        user_ids = []
        for index in range(8):
            user = User.objects.create_user(
                email=f"parallel-load-{index}@example.com",
                password="testpass123",
                first_name="Load",
                last_name=str(index),
                phone="+79990000001",
                is_active=True,
                is_email_confirmed=True,
            )
            cart = Cart.objects.create(user=user)
            CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=1)
            user_ids.append(user.pk)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda args: self._run_checkout_for_user_once(*args),
                    [(user_id, f"parallel-load-{user_id}") for user_id in user_ids],
                )
            )

        ok_results = [result for result in results if result[0] == "ok"]
        error_results = [result for result in results if result[0] == "error"]

        self.variant.refresh_from_db()
        self.assertEqual(len(ok_results), 3, results)
        self.assertEqual(len(error_results), 5, results)
        self.assertEqual(Order.objects.filter(user_id__in=user_ids).count(), 3)
        self.assertEqual(Payment.objects.filter(order__user_id__in=user_ids).count(), 3)
        self.assertGreaterEqual(self.variant.quantity, 0)
        self.assertGreaterEqual(self.variant.reserved_quantity, 0)
        self.assertLessEqual(self.variant.reserved_quantity, self.variant.quantity)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 3)

    def test_parallel_cancellation_returns_stock_only_once(self):
        """Параллельная отмена одного заказа должна быть идемпотентной."""
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
        self.assertEqual(self.variant.reserved_quantity, 0)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_dashboard_status_updates_are_serialized(self):
        """Параллельные staff-обновления статуса не должны нарушать flow."""
        order = self._create_cancellable_order()
        processing_started = Event()
        original_apply_status = OrderStatusPolicy.apply_status

        def delayed_apply_status(order_obj, status_key):
            if status_key == "processing":
                processing_started.set()
                sleep(0.2)
            return original_apply_status(order_obj, status_key)

        with patch(
            "orders.application.dashboard_order_flow.OrderStatusPolicy.apply_status",
            side_effect=delayed_apply_status,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                processing_future = executor.submit(self._run_dashboard_status_once, order.id, "processing")
                self.assertTrue(processing_started.wait(timeout=2), "Обновление до processing не стартовало вовремя.")
                cancelled_future = executor.submit(self._run_dashboard_status_once, order.id, "cancelled")
                processing_result = processing_future.result()
                cancelled_result = cancelled_future.result()

        self.assertEqual(processing_result[0], "ok", (processing_result, cancelled_result))
        self.assertEqual(cancelled_result[0], "error", (processing_result, cancelled_result))
        self.assertIn("нельзя отменить", cancelled_result[2].lower())

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.PACKING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 2)


class DashboardOrderFlowServiceTest(TestCase):
    """Тесты application-слоя staff dashboard для заказов."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="staff-flow@example.com",
            password="testpass123",
            first_name="Мария",
            last_name="Петрова",
            phone="+79991112233",
            is_active=True,
        )
        self.category = Category.objects.create(name="Кепки")
        self.product = Product.objects.create(name="Кепка клуба", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("cap.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Черный",
            price=Decimal("1500.00"),
            quantity=5,
            reserved_quantity=2,
            image=self.image,
        )
        self.order = Order.objects.create(
            number="ORD-DASH-1",
            user=self.user,
            recipient_name="Мария Петрова",
            email=self.user.email,
            phone=self.user.phone,
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("3000.00"),
            total_amount=Decimal("3000.00"),
            confirmed_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=self.order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("3000.00"),
        )
        self.service = DashboardOrderFlowService(
            cancellation_service=OrderCancellationService(),
            payment_service=ManualPaymentUpdateService(),
        )

    def test_issued_status_requires_successful_payment(self):
        with self.assertRaises(DashboardOrderFlowError):
            self.service.update_order_status(self.order, "issued")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.NEW)

    def test_cannot_skip_directly_from_new_to_issued_even_if_payment_succeeded(self):
        self.order.payment_status = Order.PaymentStatus.SUCCEEDED
        self.order.save(update_fields=["payment_status", "updated_at"])

        with self.assertRaises(DashboardOrderFlowError):
            self.service.update_order_status(self.order, "issued")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.NEW)

    def test_ready_order_can_be_issued_after_successful_payment(self):
        self.order.payment_status = Order.PaymentStatus.SUCCEEDED
        self.order.fulfillment_status = Order.FulfillmentStatus.RESERVED
        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["payment_status", "fulfillment_status", "status", "updated_at"])

        result = self.service.update_order_status(self.order, "issued", actor=self.user)

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
        self.assertIsNotNone(self.order.issued_at)
        self.assertEqual(self.variant.quantity, 3)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_status_update_creates_dashboard_transition_audit(self):
        result = self.service.update_order_status(self.order, "processing", actor=self.user)

        self.order.refresh_from_db()
        self.assertTrue(result.changed)
        transitions = list(OrderStatusTransition.objects.filter(order=self.order).order_by("id"))
        self.assertEqual(len(transitions), 3)
        self.assertEqual(transitions[0].transition_type, OrderStatusTransition.TransitionType.DASHBOARD_STATUS)
        self.assertEqual(transitions[0].from_value, "new")
        self.assertEqual(transitions[0].to_value, "processing")
        self.assertEqual(transitions[1].transition_type, OrderStatusTransition.TransitionType.ORDER_STATUS)
        self.assertEqual(transitions[1].from_value, Order.Status.PLACED)
        self.assertEqual(transitions[1].to_value, Order.Status.PROCESSING)
        self.assertEqual(transitions[2].transition_type, OrderStatusTransition.TransitionType.FULFILLMENT_STATUS)
        self.assertEqual(transitions[2].from_value, Order.FulfillmentStatus.NEW)
        self.assertEqual(transitions[2].to_value, Order.FulfillmentStatus.PACKING)
        self.assertTrue(all(transition.changed_by_id == self.user.id for transition in transitions), transitions)

    def test_noop_status_update_returns_non_changed_result(self):
        result = self.service.update_order_status(self.order, "new")

        self.order.refresh_from_db()
        self.assertFalse(result.changed)
        self.assertEqual(result.message, "Статус заказа уже установлен.")
        self.assertEqual(self.order.status, Order.Status.PLACED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.NEW)

    def test_cancelled_status_delegates_to_cancellation_service(self):
        result = self.service.update_order_status(self.order, "cancelled")

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(self.order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(self.variant.quantity, 5)
        self.assertEqual(self.variant.reserved_quantity, 0)

    def test_payment_status_update_returns_success_message(self):
        result = self.service.update_payment_status(self.order, Order.PaymentStatus.SUCCEEDED, actor=self.user)

        self.order.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.message, "Статус оплаты обновлен.")
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)
        transition = OrderStatusTransition.objects.get(
            order=self.order,
            transition_type=OrderStatusTransition.TransitionType.PAYMENT_STATUS,
        )
        self.assertEqual(transition.from_value, Order.PaymentStatus.PENDING)
        self.assertEqual(transition.to_value, Order.PaymentStatus.SUCCEEDED)
        self.assertEqual(transition.changed_by_id, self.user.id)


class OrderNotificationServiceIntegrationTest(TestCase):
    """Тесты планирования уведомлений по заказу."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="notify@example.com",
            password="testpass123",
            first_name="Анна",
            last_name="Смирнова",
            phone="+79992223344",
            is_active=True,
            is_email_confirmed=True,
        )
        self.category = Category.objects.create(name="Уведомления")
        self.product = Product.objects.create(name="Шапка клуба", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("hat.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="L",
            color="Черный",
            price=Decimal("1900.00"),
            quantity=6,
            image=self.image,
        )

    @patch("orders.application.order_notification_service.send_staff_new_order_notification")
    @patch("orders.application.order_notification_service.send_order_notification")
    def test_checkout_schedules_created_notification(
        self,
        mock_send_order_notification,
        mock_send_staff_new_order_notification,
    ):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=1)
        service = CheckoutService()
        request = RequestFactory().post(reverse("orders:checkout"))
        request.user = self.user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()

        with self.captureOnCommitCallbacks(execute=True):
            order = service.create_order_from_cart(
                CheckoutContext(user=self.user, cart_context=CartContextResolver().resolve_request(request)),
                cleaned_data={
                    "recipient_name": "Анна Смирнова",
                    "email": self.user.email,
                    "phone": self.user.phone,
                    "customer_comment": "",
                },
                checkout_token="notify-created",
            )

        mock_send_order_notification.delay.assert_called_once_with(order.id, "created")
        mock_send_staff_new_order_notification.delay.assert_called_once_with(order.id)

    @patch("orders.application.order_notification_service.send_order_notification")
    def test_cancellation_schedules_cancelled_notification(self, mock_send_order_notification):
        order = Order.objects.create(
            number="ORD-NOTIFY-1",
            user=self.user,
            recipient_name="Анна Смирнова",
            email=self.user.email,
            phone=self.user.phone,
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("1900.00"),
            total_amount=Decimal("1900.00"),
            confirmed_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=1,
            line_total=Decimal("1900.00"),
        )
        self.variant.reserved_quantity = 1
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            OrderCancellationService().cancel_order(order_id=order.id, user_id=self.user.id)

        mock_send_order_notification.delay.assert_called_once_with(order.id, "cancelled")

    @patch("orders.application.order_notification_service.send_order_notification")
    def test_ready_status_schedules_ready_notification(self, mock_send_order_notification):
        order = Order.objects.create(
            number="ORD-NOTIFY-2",
            user=self.user,
            recipient_name="Анна Смирнова",
            email=self.user.email,
            phone=self.user.phone,
            status=Order.Status.PROCESSING,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.PACKING,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("1900.00"),
            total_amount=Decimal("1900.00"),
            confirmed_at=timezone.now(),
        )

        with self.captureOnCommitCallbacks(execute=True):
            DashboardOrderFlowService().update_order_status(order, "ready")

        mock_send_order_notification.delay.assert_called_once_with(order.id, "ready")

    @patch("orders.application.order_notification_service.send_order_notification")
    def test_successful_manual_payment_schedules_paid_notification(self, mock_send_order_notification):
        order = Order.objects.create(
            number="ORD-NOTIFY-3",
            user=self.user,
            recipient_name="Анна Смирнова",
            email=self.user.email,
            phone=self.user.phone,
            status=Order.Status.PROCESSING,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.RESERVED,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("1900.00"),
            total_amount=Decimal("1900.00"),
            confirmed_at=timezone.now(),
        )

        with self.captureOnCommitCallbacks(execute=True):
            ManualPaymentUpdateService().update_order_payment_status(order.id, Order.PaymentStatus.SUCCEEDED)

        mock_send_order_notification.delay.assert_called_once_with(order.id, "paid")


class OrderStaffNotificationTaskTest(TestCase):
    """Тесты staff-уведомления о новом заказе."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="staff-notify-buyer@example.com",
            password="testpass123",
            first_name="Игорь",
            last_name="Петров",
            phone="+79990000001",
            is_active=True,
            is_email_confirmed=True,
        )
        self.category = Category.objects.create(name="Staff уведомления")
        self.product = Product.objects.create(name="Толстовка клуба", category=self.category)
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("hoodie.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("3500.00"),
            quantity=8,
            image=self.image,
        )
        self.order = Order.objects.create(
            number="ORD-STAFF-1",
            user=self.user,
            recipient_name="Игорь Петров",
            email=self.user.email,
            phone=self.user.phone,
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            subtotal_amount=Decimal("7000.00"),
            total_amount=Decimal("7000.00"),
            customer_comment="Позвоните за час до готовности",
            confirmed_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=self.order,
            product_variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=str(self.variant.id),
            size_snapshot=self.variant.size,
            color_snapshot=self.variant.color,
            unit_price=self.variant.price,
            quantity=2,
            line_total=Decimal("7000.00"),
        )

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        STAFF_ORDER_NOTIFICATION_EMAILS=["staff1@example.com", "staff2@example.com"],
        SITE_URL="http://localhost:8000",
    )
    @patch("orders.tasks.send_mail")
    def test_send_staff_new_order_notification_sync_sends_detailed_email(self, mock_send_mail):
        result = send_staff_new_order_notification_sync(self.order.id)

        self.assertTrue(result)
        mock_send_mail.assert_called_once()
        kwargs = mock_send_mail.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], ["staff1@example.com", "staff2@example.com"])
        self.assertIn(self.order.number, kwargs["subject"])
        self.assertIn("Номер заказа", kwargs["message"])
        self.assertIn("Сумма заказа", kwargs["message"])
        self.assertIn(self.order.email, kwargs["message"])
        self.assertIn(self.order.phone, kwargs["message"])
        self.assertIn(self.product.name, kwargs["message"])
        self.assertIn(reverse("store:dashboard_order_detail", kwargs={"pk": self.order.pk}), kwargs["message"])

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        STAFF_ORDER_NOTIFICATION_EMAILS=[],
    )
    @patch("orders.tasks.send_mail")
    def test_send_staff_new_order_notification_sync_skips_when_staff_list_is_empty(self, mock_send_mail):
        result = send_staff_new_order_notification_sync(self.order.id)

        self.assertFalse(result)
        mock_send_mail.assert_not_called()

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        STAFF_ORDER_NOTIFICATION_EMAILS=["staff1@example.com"],
    )
    @patch("orders.tasks.logger.exception")
    @patch("orders.tasks.send_mail", side_effect=RuntimeError("smtp unavailable"))
    def test_send_staff_new_order_notification_sync_logs_error_context(
        self,
        mock_send_mail,
        mock_logger_exception,
    ):
        result = send_staff_new_order_notification_sync(self.order.id)

        self.assertFalse(result)
        mock_send_mail.assert_called_once()
        mock_logger_exception.assert_called_once()
        log_extra = mock_logger_exception.call_args.kwargs["extra"]
        self.assertEqual(log_extra["order_id"], self.order.id)
        self.assertEqual(log_extra["event_key"], "staff_created")
        self.assertEqual(log_extra["reason"], "send_mail_failed")

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SITE_URL="http://localhost:8000",
    )
    @patch("orders.tasks.logger.exception")
    @patch("orders.tasks.send_mail", side_effect=RuntimeError("smtp unavailable"))
    def test_send_order_notification_sync_logs_error_context(
        self,
        mock_send_mail,
        mock_logger_exception,
    ):
        result = send_order_notification_sync(self.order.id, "created")

        self.assertFalse(result)
        mock_send_mail.assert_called_once()
        mock_logger_exception.assert_called_once()
        log_extra = mock_logger_exception.call_args.kwargs["extra"]
        self.assertEqual(log_extra["order_id"], self.order.id)
        self.assertEqual(log_extra["event_key"], "created")
        self.assertEqual(log_extra["reason"], "send_mail_failed")


class OrderNotificationTaskRetryConfigurationTest(SimpleTestCase):
    def _assert_retry_settings(self, task):
        self.assertEqual(task.autoretry_for, (NotificationDeliveryError,))
        self.assertTrue(task.retry_backoff)
        self.assertEqual(task.retry_backoff_max, 300)
        self.assertTrue(task.retry_jitter)
        self.assertEqual(task.retry_kwargs, {"max_retries": 5})

    def test_send_order_notification_has_retry_backoff(self):
        self._assert_retry_settings(send_order_notification)

    def test_send_staff_new_order_notification_has_retry_backoff(self):
        self._assert_retry_settings(send_staff_new_order_notification)
