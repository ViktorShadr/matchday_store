import os
import time
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import ANY, call, patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase, tag
from django.urls import reverse

from orders.models import Order, OrderStatusTransition
from orders.tasks import send_order_notification
from payments.models import Payment
from store.models import Cart, Category, Product, ProductImage, ProductVariant
from users.models import User


@tag("smoke", "e2e")
class SalesFlowSmokeE2ETest(TestCase):
    """Smoke E2E: регистрация -> checkout -> уведомления -> dashboard -> выдача."""

    def setUp(self):
        self.customer_client = Client()
        self.dashboard_client = Client()

        self.dashboard_user = User.objects.create_superuser(
            email="smoke-dashboard-admin@example.com",
            password="smokedashpass123",
        )
        self.category = Category.objects.create(name="Smoke E2E категория")
        self.product = Product.objects.create(
            name="Smoke E2E товар",
            description="Тестовый товар для сквозного smoke сценария",
            category=self.category,
            is_on_sale=True,
        )
        self.image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("smoke-product.jpg", b"fake_image_data", content_type="image/jpeg"),
            is_primary=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Синий",
            price=Decimal("1990.00"),
            quantity=10,
            image=self.image,
        )

    def test_full_sales_flow_smoke_e2e(self):
        user_email = f"smoke-user-{uuid4().hex[:8]}@example.com"
        user_password = "smokeuserpass123"

        with (
            patch("users.views.send_confirmation_email") as mock_send_confirmation_email,
            patch("users.views.send_welcome_email") as mock_send_welcome_email,
            patch(
                "orders.application.order_notification_service.send_order_notification"
            ) as mock_send_order_notification,
            patch(
                "orders.application.order_notification_service.send_staff_new_order_notification"
            ) as mock_send_staff_new_order_notification,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                registration_response = self.customer_client.post(
                    reverse("users:registration"),
                    data={
                        "email": user_email,
                        "password1": user_password,
                        "password2": user_password,
                    },
                )

            self.assertRedirects(registration_response, reverse("users:login"))
            customer_user = User.objects.get(email=user_email)
            self.assertTrue(customer_user.is_active)
            self.assertFalse(customer_user.is_email_confirmed)
            self.assertIsNotNone(customer_user.email_token)
            mock_send_confirmation_email.delay.assert_called_once_with(user_email, ANY)

            confirmation_response = self.customer_client.get(
                reverse("users:confirm_email", kwargs={"token": customer_user.email_token})
            )
            self.assertRedirects(
                confirmation_response,
                reverse("users:profile_detail", kwargs={"pk": customer_user.pk}),
            )
            customer_user.refresh_from_db()
            self.assertTrue(customer_user.is_email_confirmed)
            mock_send_welcome_email.delay.assert_called_once_with(user_email)

            add_to_cart_response = self.customer_client.post(
                reverse("store:add_to_cart"),
                data={"variant_id": str(self.variant.id), "quantity": "2"},
            )
            self.assertEqual(add_to_cart_response.status_code, 200)
            self.assertJSONEqual(
                add_to_cart_response.content.decode("utf-8"),
                {
                    "success": True,
                    "message": f'Товар "{self.product.name}" добавлен в корзину',
                    "cart_total": 2,
                },
            )

            checkout_page_response = self.customer_client.get(reverse("orders:checkout"))
            self.assertEqual(checkout_page_response.status_code, 200)
            checkout_token = self.customer_client.session.get("_checkout_token")
            self.assertTrue(checkout_token)

            with self.captureOnCommitCallbacks(execute=True):
                checkout_response = self.customer_client.post(
                    reverse("orders:checkout"),
                    data={
                        "recipient_name": "Smoke Buyer",
                        "email": user_email,
                        "phone": "+79990000011",
                        "customer_comment": "Smoke E2E checkout",
                        "checkout_token": checkout_token,
                    },
                )

            order = Order.objects.get(user=customer_user)
            self.assertRedirects(
                checkout_response,
                reverse("orders:checkout_success", kwargs={"pk": order.pk}),
            )
            self.assertEqual(order.status, Order.Status.PLACED)
            self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
            self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.NEW)

            payment = Payment.objects.get(order=order, provider=Payment.Provider.MANUAL)
            self.assertEqual(payment.status, Payment.Status.PENDING)
            self.assertEqual(payment.amount, Decimal("3980.00"))

            self.variant.refresh_from_db()
            self.assertEqual(self.variant.quantity, 8)
            customer_cart = Cart.objects.get(user=customer_user)
            self.assertEqual(customer_cart.items.count(), 0)

            mock_send_staff_new_order_notification.delay.assert_called_once_with(order.id)
            self.assertIn(call(order.id, "created"), mock_send_order_notification.delay.call_args_list)

            self.dashboard_client.force_login(self.dashboard_user)

            with self.captureOnCommitCallbacks(execute=True):
                payment_update_response = self.dashboard_client.post(
                    reverse("store:dashboard_order_payment_status_update", kwargs={"pk": order.pk}),
                    data={"payment_status": Order.PaymentStatus.SUCCEEDED},
                )
            self.assertRedirects(
                payment_update_response,
                reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}),
            )

            with self.captureOnCommitCallbacks(execute=True):
                ready_response = self.dashboard_client.post(
                    reverse("store:dashboard_order_status_update", kwargs={"pk": order.pk}),
                    data={"status": "ready"},
                )
            self.assertRedirects(
                ready_response,
                reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}),
            )

            with self.captureOnCommitCallbacks(execute=True):
                issued_response = self.dashboard_client.post(
                    reverse("store:dashboard_order_status_update", kwargs={"pk": order.pk}),
                    data={"status": "issued"},
                )
            self.assertRedirects(
                issued_response,
                reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}),
            )

            order.refresh_from_db()
            self.assertEqual(order.payment_status, Order.PaymentStatus.SUCCEEDED)
            self.assertEqual(order.status, Order.Status.DELIVERED)
            self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
            self.assertIsNotNone(order.issued_at)

            self.assertIn(call(order.id, "paid"), mock_send_order_notification.delay.call_args_list)
            self.assertIn(call(order.id, "ready"), mock_send_order_notification.delay.call_args_list)
            self.assertTrue(
                OrderStatusTransition.objects.filter(
                    order=order,
                    transition_type=OrderStatusTransition.TransitionType.DASHBOARD_STATUS,
                    from_value="ready",
                    to_value="issued",
                ).exists()
            )


@tag("smoke", "e2e", "worker")
@skipUnless(
    os.getenv("RUN_SMOKE_E2E") == "1",
    "Worker smoke E2E отключен. Установите RUN_SMOKE_E2E=1 для запуска.",
)
class WorkerExecutionSmokeE2ETest(TransactionTestCase):
    """Smoke E2E: проверка, что Celery worker реально исполняет задачи."""

    def test_worker_executes_notification_task(self):
        celery_task_result = send_order_notification.delay(order_id=999999999, event_key="created")
        deadline = time.monotonic() + 30

        while not celery_task_result.ready() and time.monotonic() < deadline:
            time.sleep(0.5)

        self.assertTrue(
            celery_task_result.ready(),
            "Celery task не завершилась за отведенное время. Проверьте worker/broker/result backend.",
        )
        self.assertEqual(celery_task_result.state, "SUCCESS")
        self.assertFalse(celery_task_result.result)
