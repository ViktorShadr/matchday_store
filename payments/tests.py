from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Address, Order
from payments.models import Payment

User = get_user_model()



class PaymentStatusSignalTest(TestCase):
    def setUp(self):
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
        defaults = {
            "order": self.order,
            "idempotency_key": f"idem-{Payment.objects.count() + 1}",
            "amount": Decimal("1000.00"),
        }
        defaults.update(kwargs)
        return Payment.objects.create(**defaults)

    def test_successful_payment_updates_order_payment_status(self):
        self.create_payment(status=Payment.Status.SUCCEEDED)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)

    def test_last_unsuccessful_payment_status_is_applied_to_order(self):
        self.create_payment(status=Payment.Status.PENDING)
        self.create_payment(status=Payment.Status.REQUIRES_ACTION)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REQUIRES_ACTION)

    def test_successful_payment_has_priority_over_later_failed_attempt(self):
        self.create_payment(status=Payment.Status.SUCCEEDED)
        self.create_payment(status=Payment.Status.FAILED)

        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.SUCCEEDED)

    def test_deleting_payment_recalculates_order_payment_status(self):
        pending_payment = self.create_payment(status=Payment.Status.PENDING)
        succeeded_payment = self.create_payment(status=Payment.Status.SUCCEEDED)

        succeeded_payment.delete()
        self.order.refresh_from_db()
        pending_payment.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
