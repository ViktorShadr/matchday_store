from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse

from orders.models import Order, OrderItem
from orders.services import CheckoutService
from payments.models import Payment
from store.models import Cart, CartItem, Category, Product, ProductImage, ProductVariant
from users.models import User


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

    def _build_service_request(self):
        request = self.factory.post(reverse("orders:checkout"))
        request.user = self.user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        return request

    def test_checkout_requires_authentication(self):
        """Гость должен быть перенаправлен на логин."""
        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

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
