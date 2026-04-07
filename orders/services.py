from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from orders.models import Order, OrderItem
from payments.models import Payment
from store.models import ProductVariant
from store.services.cart_service import CartService


class CheckoutError(Exception):
    """Бизнес-ошибка оформления заказа."""


class CheckoutService:
    """Сервис оформления заказа из корзины."""

    @staticmethod
    def build_order_number() -> str:
        """Собрать компактный номер заказа."""
        return f"ORD-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"

    @classmethod
    @transaction.atomic
    def create_order_from_cart(cls, request, cleaned_data):
        """Создать заказ, списать остатки и очистить корзину."""
        cart = CartService.get_or_create_cart(request)
        cart_items = list(
            cart.items.select_related("product_variant__product").select_for_update().order_by("pk")
        )

        if not cart_items:
            raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")

        locked_variant_ids = [item.product_variant_id for item in cart_items]
        locked_variants = {
            variant.id: variant
            for variant in ProductVariant.objects.select_for_update().filter(id__in=locked_variant_ids).select_related(
                "product"
            )
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

        order = Order.objects.create(
            number=cls.build_order_number(),
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
        OrderItem.objects.bulk_create(order_items)

        Payment.objects.create(
            order=order,
            provider=Payment.Provider.MANUAL,
            idempotency_key=uuid4().hex,
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
