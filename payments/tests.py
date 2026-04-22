from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Address, Order
from payments.application import PaymentWorkflowService
from payments.models import Payment

User = get_user_model()


class PaymentWorkflowTest(TestCase):
    """Тесты явного workflow синхронизации платежа и заказа."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.user = User.objects.create_user(email="payment@example.com", password="testpass123")
        self.address = Address.objects.create(
            user=self.user,
            recipient_name="Test User",
            phone="+79990000000",
            city="Moscow",
            postal_code="101000",
            street="Tverskaya",
            house="1",
        )
        self.order = Order.objects.create(
            number="ORDER-1001",
            user=self.user,
            email=self.user.email,
            phone="+79990000000",
            delivery_address=self.address,
            subtotal_amount=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
        )

    def create_payment(self, **kwargs):
        """Создает payment через workflow."""
        defaults = {
            "order": self.order,
            "idempotency_key": f"idem-{Payment.objects.count() + 1}",
            "amount": Decimal("1000.00"),
        }
        defaults.update(kwargs)
        return PaymentWorkflowService.create_payment(**defaults)

    def test_successful_payment_updates_order_payment_status(self):
        """Проверяет сценарий 'successful payment updates order payment status'."""
        self.create_payment(status=Payment.Status.SUCCEEDED)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)

    def test_last_unsuccessful_payment_status_is_applied_to_order(self):
        """Проверяет сценарий 'last unsuccessful payment status is applied to order'."""
        self.create_payment(status=Payment.Status.PENDING)
        self.create_payment(status=Payment.Status.REQUIRES_ACTION)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REQUIRES_ACTION)

    def test_successful_payment_has_priority_over_later_failed_attempt(self):
        """Проверяет сценарий 'successful payment has priority over later failed attempt'."""
        self.create_payment(status=Payment.Status.SUCCEEDED)
        self.create_payment(status=Payment.Status.FAILED)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)

    def test_deleting_payment_recalculates_order_payment_status(self):
        """Проверяет сценарий 'deleting payment recalculates order payment status'."""
        pending_payment = self.create_payment(status=Payment.Status.PENDING)
        succeeded_payment = self.create_payment(status=Payment.Status.SUCCEEDED)

        PaymentWorkflowService.delete_payment(succeeded_payment)
        self.order.refresh_from_db()
        pending_payment.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
