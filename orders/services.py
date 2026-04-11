from decimal import Decimal
from uuid import uuid4
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from orders.models import Order, OrderItem
from payments.models import Payment
from store.repositories import IProductVariantRepository
from store.repositories import ProductVariantRepository
from orders.repositories import IOrderRepository, IPaymentRepository
from orders.repositories import OrderRepository, PaymentRepository
from store.services.cart_service import CartService
from store.services.interfaces import ICheckoutService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()


class CheckoutError(Exception):
    """Бизнес-ошибка оформления заказа."""


class CheckoutService(ICheckoutService):
    """
    Сервис оформления заказа из корзины.
    
    Реализует DIP через dependency injection репозиториев.
    """

    def __init__(
        self,
        cart_service: Optional[CartService] = None,
        product_variant_repository: Optional[IProductVariantRepository] = None,
        order_repository: Optional[IOrderRepository] = None,
        payment_repository: Optional[IPaymentRepository] = None,
    ):
        """
        Инициализация сервиса с возможностью DI.

        Args:
            cart_service: Сервис корзины (по умолчанию глобальный экземпляр)
            product_variant_repository: Репозиторий вариантов товаров
            order_repository: Репозиторий заказов
            payment_repository: Репозиторий платежей
        """
        self.cart_service = cart_service or CartService()
        self.product_variant_repository = product_variant_repository or ProductVariantRepository()
        self.order_repository = order_repository or OrderRepository()
        self.payment_repository = payment_repository or PaymentRepository()

    @staticmethod
    def build_order_number() -> str:
        """Собрать компактный номер заказа."""
        return f"ORD-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"

    @staticmethod
    def build_checkout_idempotency_key(checkout_token: Optional[str]) -> str:
        """Собрать idempotency key для checkout."""
        if checkout_token:
            return f"checkout-{checkout_token}"
        return uuid4().hex

    def create_order_from_cart(self, request, cleaned_data, checkout_token: Optional[str] = None):
        """Создать заказ, списать остатки и очистить корзину."""
        payment_idempotency_key = self.build_checkout_idempotency_key(checkout_token)

        existing_payment = None
        if checkout_token:
            existing_payment = self.payment_repository.get_payment_by_idempotency_key(payment_idempotency_key)
            if existing_payment and existing_payment.order.user_id == request.user.id:
                return existing_payment.order

        try:
            with transaction.atomic():
                cart = self.cart_service.get_or_create_cart(request)
                cart_items = list(
                    cart.items.select_related("product_variant__product").select_for_update().order_by("pk")
                )

                if not cart_items:
                    raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")

                locked_variant_ids = [item.product_variant_id for item in cart_items]
                locked_variants = {
                    variant.id: variant
                    for variant in self.product_variant_repository.get_variants_for_update(locked_variant_ids)
                }

                subtotal_amount = Decimal("0.00")
                order_items = []

                for cart_item in cart_items:
                    variant = locked_variants.get(cart_item.product_variant_id)
                    if variant is None:
                        raise CheckoutError("Один из товаров больше недоступен. Обновите корзину.")

                    if variant.quantity < cart_item.quantity:
                        raise CheckoutError(
                            f'Недостаточно товара "{variant.product.name}" на складе. '
                            f"Доступно: {variant.quantity} шт."
                        )

                    line_total = variant.price * cart_item.quantity
                    subtotal_amount += line_total
                    order_items.append(
                        OrderItem(
                            product_variant=variant,
                            product_name_snapshot=variant.product.name,
                            sku_snapshot=str(variant.id),
                            size_snapshot=variant.size,
                            color_snapshot=variant.color,
                            unit_price=variant.price,
                            quantity=cart_item.quantity,
                            line_total=line_total,
                        )
                    )

                order = self.order_repository.create_order(
                    number=self.build_order_number(),
                    user=request.user,
                    recipient_name=cleaned_data["recipient_name"],
                    email=cleaned_data["email"],
                    phone=cleaned_data["phone"],
                    status=Order.Status.PLACED,
                    payment_status=Order.PaymentStatus.PENDING,
                    fulfillment_status=Order.FulfillmentStatus.NEW,
                    delivery_method=Order.DeliveryMethod.PICKUP,
                    delivery_address=None,
                    pickup_point_code=settings.STORE_PICKUP_LOCATION_CODE,
                    subtotal_amount=subtotal_amount,
                    delivery_amount=Decimal("0.00"),
                    discount_amount=Decimal("0.00"),
                    total_amount=subtotal_amount,
                    customer_comment=cleaned_data.get("customer_comment", "").strip(),
                    source_cart_id=cart.id,
                    confirmed_at=timezone.now(),
                )

                for item in order_items:
                    item.order = order
                self.order_repository.bulk_create_order_items(order_items)

                self.payment_repository.create_payment(
                    order=order,
                    provider=Payment.Provider.MANUAL,
                    idempotency_key=payment_idempotency_key,
                    status=Payment.Status.PENDING,
                    amount=subtotal_amount,
                    currency=order.currency,
                    raw_request={
                        "payment_method": "pay_on_receipt",
                        "pickup_location_code": settings.STORE_PICKUP_LOCATION_CODE,
                    },
                )

                for cart_item in cart_items:
                    variant = locked_variants[cart_item.product_variant_id]
                    variant.quantity -= cart_item.quantity
                    variant.save(update_fields=["quantity", "updated_at"])

                cart.items.all().delete()
                return order
        except IntegrityError as exc:
            if checkout_token:
                existing_payment = self.payment_repository.get_payment_by_idempotency_key(payment_idempotency_key)
                if existing_payment and existing_payment.order.user_id == request.user.id:
                    return existing_payment.order
            raise CheckoutError("Заказ уже обрабатывается. Обновите страницу и проверьте статус заказа.") from exc
