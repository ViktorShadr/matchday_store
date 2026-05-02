from decimal import Decimal
from uuid import uuid4
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from orders.application.checkout_context import CheckoutContext
from orders.application.order_notification_service import OrderNotificationService
from orders.models import Order, OrderItem, OrderStatusTransition
from payments.application import PaymentWorkflowService
from payments.models import Payment
from store.repositories import IProductVariantRepository
from store.repositories import ProductVariantRepository
from orders.repositories import IOrderRepository, IPaymentRepository
from orders.repositories import OrderRepository, PaymentRepository
from store.services.cart_service import CartService
from store.services.interfaces import ICheckoutService


class CheckoutError(Exception):
    """Бизнес-ошибка оформления заказа."""


class OrderCancellationError(Exception):
    """Бизнес-ошибка отмены заказа."""


class ManualPaymentUpdateError(Exception):
    """Бизнес-ошибка обновления оплаты заказа."""


class CheckoutService(ICheckoutService):
    """
    Сервис оформления заказа из корзины.
    
    Реализует DIP через dependency injection репозиториев.
    """

    ACTIVE_ORDER_FINAL_STATUSES = frozenset(
        {
            Order.Status.CANCELLED,
            Order.Status.DELIVERED,
            Order.Status.REFUNDED,
        }
    )
    ACTIVE_ORDER_FINAL_FULFILLMENT_STATUSES = frozenset(
        {
            Order.FulfillmentStatus.CANCELLED,
            Order.FulfillmentStatus.DELIVERED,
            Order.FulfillmentStatus.RETURNED,
        }
    )

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
    def _normalize_snapshot_text(value) -> str:
        """Привести snapshot-поля к строке (OrderItem snapshot поля non-nullable)."""
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def build_checkout_idempotency_key(checkout_token: Optional[str], user_id: Optional[int] = None) -> str:
        """Собрать idempotency key для checkout с учетом пользователя."""
        if checkout_token:
            if user_id is not None:
                return f"checkout-{user_id}-{checkout_token}"
            return f"checkout-{checkout_token}"
        return uuid4().hex

    def _find_existing_checkout_payment(self, checkout_token: Optional[str], user_id: int):
        """Найти уже созданный payment для checkout (новый и legacy ключи)."""
        if not checkout_token:
            return None

        current_key = self.build_checkout_idempotency_key(checkout_token, user_id=user_id)
        existing_payment = self.payment_repository.get_payment_by_idempotency_key(current_key)
        if existing_payment and existing_payment.order.user_id == user_id:
            return existing_payment

        # Backward compatibility for keys created before user-scoped idempotency.
        legacy_key = self.build_checkout_idempotency_key(checkout_token)
        existing_legacy_payment = self.payment_repository.get_payment_by_idempotency_key(legacy_key)
        if existing_legacy_payment and existing_legacy_payment.order.user_id == user_id:
            return existing_legacy_payment

        return None

    @classmethod
    def _count_active_unpaid_orders(cls, user_id: int) -> int:
        """Посчитать открытые неоплаченные заказы пользователя."""
        return (
            Order.objects.filter(user_id=user_id)
            .exclude(status__in=cls.ACTIVE_ORDER_FINAL_STATUSES)
            .exclude(fulfillment_status__in=cls.ACTIVE_ORDER_FINAL_FULFILLMENT_STATUSES)
            .exclude(payment_status=Order.PaymentStatus.SUCCEEDED)
            .count()
        )

    @classmethod
    def _ensure_active_order_limit(cls, user_id: int) -> None:
        max_active_orders = settings.CHECKOUT_MAX_ACTIVE_ORDERS
        if max_active_orders <= 0:
            return

        active_orders_count = cls._count_active_unpaid_orders(user_id)
        if active_orders_count >= max_active_orders:
            raise CheckoutError(
                "У вас уже есть активные неоплаченные заказы. "
                "Получите, оплатите или отмените один из них перед новым оформлением."
            )

    @staticmethod
    def _ensure_sku_quantity_limit(cart_item, variant) -> None:
        max_qty_per_sku = settings.CHECKOUT_MAX_QTY_PER_SKU
        if max_qty_per_sku <= 0 or cart_item.quantity <= max_qty_per_sku:
            return

        raise CheckoutError(
            f'Нельзя заказать более {max_qty_per_sku} шт. одного товара "{variant.product.name}" за раз.'
        )

    @staticmethod
    def _lock_checkout_user(user_id: int) -> None:
        get_user_model().objects.select_for_update().only("id").get(pk=user_id)

    def create_order_from_cart(
        self,
        checkout_context: CheckoutContext,
        cleaned_data,
        checkout_token: Optional[str] = None,
    ):
        """Создать заказ, списать остатки и очистить корзину."""
        payment_idempotency_key = self.build_checkout_idempotency_key(checkout_token, user_id=checkout_context.user_id)

        existing_payment = self._find_existing_checkout_payment(checkout_token, checkout_context.user_id)
        if existing_payment:
            return existing_payment.order

        self._ensure_active_order_limit(checkout_context.user_id)

        order = None
        unavailable_only_error = None

        try:
            with transaction.atomic():
                self._lock_checkout_user(checkout_context.user_id)
                existing_payment = self._find_existing_checkout_payment(
                    checkout_token,
                    checkout_context.user_id,
                )
                if existing_payment:
                    return existing_payment.order
                self._ensure_active_order_limit(checkout_context.user_id)

                cart = checkout_context.cart_context.cart
                cart_items = list(
                    cart.items.select_related("product_variant__product").select_for_update().order_by("pk")
                )

                if not cart_items:
                    if checkout_token:
                        # Повторно проверяем idempotency после захвата блокировок:
                        # в параллельном submit первый запрос мог уже создать заказ и очистить корзину.
                        existing_payment = self._find_existing_checkout_payment(checkout_token, checkout_context.user_id)
                        if existing_payment:
                            return existing_payment.order
                    raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")

                locked_variant_ids = [item.product_variant_id for item in cart_items]
                locked_variants = {
                    variant.id: variant
                    for variant in self.product_variant_repository.get_variants_for_update(locked_variant_ids)
                }

                subtotal_amount = Decimal("0.00")
                order_items = []
                processable_cart_items = []
                skipped_cart_item_ids = []

                for cart_item in cart_items:
                    variant = locked_variants.get(cart_item.product_variant_id)
                    if variant is None:
                        skipped_cart_item_ids.append(cart_item.pk)
                        continue

                    # Позиции, которые нельзя оформить (сняты с продажи или нулевой остаток),
                    # исключаем из checkout и удаляем из корзины в этой же транзакции.
                    if not variant.product.is_on_sale or variant.quantity <= 0:
                        skipped_cart_item_ids.append(cart_item.pk)
                        continue

                    self._ensure_sku_quantity_limit(cart_item, variant)

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
                            size_snapshot=self._normalize_snapshot_text(variant.size),
                            color_snapshot=self._normalize_snapshot_text(variant.color),
                            unit_price=variant.price,
                            quantity=cart_item.quantity,
                            line_total=line_total,
                        )
                    )
                    processable_cart_items.append(cart_item)

                if skipped_cart_item_ids:
                    cart.items.filter(pk__in=skipped_cart_item_ids).delete()

                if not order_items:
                    unavailable_only_error = (
                        "В корзине не осталось доступных товаров. "
                        "Недоступные позиции удалены."
                    )
                else:
                    order = self.order_repository.create_order(
                        number=self.build_order_number(),
                        user=checkout_context.user,
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

                    PaymentWorkflowService.create_payment(
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

                    for cart_item in processable_cart_items:
                        variant = locked_variants[cart_item.product_variant_id]
                        variant.quantity -= cart_item.quantity
                        variant.save(update_fields=["quantity", "updated_at"])

                    processable_cart_item_ids = [item.pk for item in processable_cart_items]
                    if processable_cart_item_ids:
                        cart.items.filter(pk__in=processable_cart_item_ids).delete()
                    OrderNotificationService.schedule_created(order.id)
        except IntegrityError as exc:
            if checkout_token:
                existing_payment = self._find_existing_checkout_payment(checkout_token, checkout_context.user_id)
                if existing_payment:
                    return existing_payment.order
            raise CheckoutError("Заказ уже обрабатывается. Обновите страницу и проверьте статус заказа.") from exc

        if order:
            return order

        if unavailable_only_error:
            raise CheckoutError(unavailable_only_error)

        raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")


class OrderCancellationService:
    """Сервис безопасной отмены заказа с возвратом остатков."""

    CANCELLABLE_ORDER_STATUSES = frozenset(
        {
            Order.Status.PLACED,
            Order.Status.AWAITING_PAYMENT,
        }
    )
    CANCELLABLE_FULFILLMENT_STATUSES = frozenset(
        {
            Order.FulfillmentStatus.NEW,
            Order.FulfillmentStatus.RESERVED,
        }
    )
    NON_CANCELLABLE_PAYMENT_STATUSES = frozenset(
        {
            Order.PaymentStatus.SUCCEEDED,
            Order.PaymentStatus.REFUNDED,
        }
    )

    def __init__(self, product_variant_repository: Optional[IProductVariantRepository] = None):
        self.product_variant_repository = product_variant_repository or ProductVariantRepository()

    @classmethod
    def _ensure_order_can_be_cancelled(cls, order: Order) -> None:
        if order.status not in cls.CANCELLABLE_ORDER_STATUSES:
            raise OrderCancellationError(
                f'Заказ в статусе "{order.get_status_display()}" нельзя отменить.'
            )

        if order.fulfillment_status not in cls.CANCELLABLE_FULFILLMENT_STATUSES:
            raise OrderCancellationError(
                f'Заказ в статусе исполнения "{order.get_fulfillment_status_display()}" нельзя отменить.'
            )

        if order.payment_status in cls.NON_CANCELLABLE_PAYMENT_STATUSES:
            raise OrderCancellationError(
                f'Заказ в статусе оплаты "{order.get_payment_status_display()}" нельзя отменить.'
            )

    @classmethod
    def can_be_cancelled(cls, order: Order) -> bool:
        """Проверить, можно ли отменить заказ согласно доменным правилам."""
        if order.status == Order.Status.CANCELLED:
            return False

        try:
            cls._ensure_order_can_be_cancelled(order)
        except OrderCancellationError:
            return False
        return True

    def cancel_order(self, order_id: int, user_id: Optional[int] = None, actor=None) -> Order:
        """
        Отменить заказ и вернуть остатки на склад.

        Повторный вызов для уже отмененного заказа безопасен (идемпотентный no-op).
        """
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist as exc:
                raise OrderCancellationError("Заказ не найден.") from exc

            if user_id is not None and order.user_id != user_id:
                raise OrderCancellationError("Недостаточно прав для отмены этого заказа.")

            if order.status == Order.Status.CANCELLED:
                return order

            self._ensure_order_can_be_cancelled(order)

            order_items = list(order.items.select_related("product_variant").order_by("pk"))
            variant_ids = sorted({item.product_variant_id for item in order_items if item.product_variant_id})
            locked_variants = {
                variant.id: variant for variant in self.product_variant_repository.get_variants_for_update(variant_ids)
            }

            for order_item in order_items:
                if not order_item.product_variant_id:
                    continue

                variant = locked_variants.get(order_item.product_variant_id)
                if variant is None:
                    continue

                variant.quantity += order_item.quantity
                variant.save(update_fields=["quantity", "updated_at"])

            previous_order_status = order.status
            previous_fulfillment_status = order.fulfillment_status
            previous_payment_status = order.payment_status

            order.status = Order.Status.CANCELLED
            order.fulfillment_status = Order.FulfillmentStatus.CANCELLED
            order.payment_status = Order.PaymentStatus.CANCELLED
            order.cancelled_at = timezone.now()
            order.save(
                update_fields=[
                    "status",
                    "fulfillment_status",
                    "payment_status",
                    "cancelled_at",
                    "updated_at",
                ]
            )
            OrderStatusTransition.log_if_changed(
                order=order,
                transition_type=OrderStatusTransition.TransitionType.ORDER_STATUS,
                from_value=previous_order_status,
                to_value=order.status,
                changed_by=actor,
            )
            OrderStatusTransition.log_if_changed(
                order=order,
                transition_type=OrderStatusTransition.TransitionType.FULFILLMENT_STATUS,
                from_value=previous_fulfillment_status,
                to_value=order.fulfillment_status,
                changed_by=actor,
            )
            OrderStatusTransition.log_if_changed(
                order=order,
                transition_type=OrderStatusTransition.TransitionType.PAYMENT_STATUS,
                from_value=previous_payment_status,
                to_value=order.payment_status,
                changed_by=actor,
            )
            OrderNotificationService.schedule_cancelled(order.id)

            return order


class ManualPaymentUpdateService:
    """Сервис обновления статуса ручной оплаты для заказа."""

    ALLOWED_PAYMENT_STATUSES = frozenset(
        {
            Order.PaymentStatus.PENDING,
            Order.PaymentStatus.SUCCEEDED,
            Order.PaymentStatus.FAILED,
            Order.PaymentStatus.CANCELLED,
            Order.PaymentStatus.REFUNDED,
        }
    )
    RESET_PAID_AT_STATUSES = frozenset(
        {
            Order.PaymentStatus.PENDING,
            Order.PaymentStatus.FAILED,
            Order.PaymentStatus.CANCELLED,
        }
    )

    @classmethod
    def _ensure_can_update_payment(cls, order: Order, next_payment_status: str) -> None:
        if next_payment_status not in cls.ALLOWED_PAYMENT_STATUSES:
            raise ManualPaymentUpdateError("Недопустимый статус оплаты.")

        if order.delivery_method != Order.DeliveryMethod.PICKUP:
            raise ManualPaymentUpdateError("Ручное обновление оплаты доступно только для самовывоза.")

        if order.status == Order.Status.CANCELLED and next_payment_status == Order.PaymentStatus.SUCCEEDED:
            raise ManualPaymentUpdateError("Нельзя отметить оплату успешной для отмененного заказа.")

        if next_payment_status == Order.PaymentStatus.REFUNDED:
            has_successful_payment = order.payments.filter(status=Payment.Status.SUCCEEDED).exists()
            if not has_successful_payment and order.payment_status != Order.PaymentStatus.SUCCEEDED:
                raise ManualPaymentUpdateError("Нельзя выполнить возврат: успешная оплата не найдена.")

    @staticmethod
    def _build_dashboard_idempotency_key(order_id: int) -> str:
        return f"dashboard-manual-{order_id}-{uuid4().hex}"

    def update_order_payment_status(self, order_id: int, next_payment_status: str, actor=None) -> Order:
        """
        Обновить статус оплаты заказа через ручной staff-flow.

        Создает платеж manual при его отсутствии и синхронизирует
        Order.payment_status + Order.paid_at.
        """
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist as exc:
                raise ManualPaymentUpdateError("Заказ не найден.") from exc

            previous_payment_status = order.payment_status
            self._ensure_can_update_payment(order, next_payment_status)
            now = timezone.now()

            payment = (
                Payment.objects.select_for_update()
                .filter(order=order, provider=Payment.Provider.MANUAL)
                .order_by("-updated_at", "-created_at", "-pk")
                .first()
            )

            if payment is None:
                payment = PaymentWorkflowService.create_payment(
                    order=order,
                    provider=Payment.Provider.MANUAL,
                    idempotency_key=self._build_dashboard_idempotency_key(order.id),
                    status=next_payment_status,
                    amount=order.total_amount,
                    currency=order.currency,
                    paid_at=now if next_payment_status == Order.PaymentStatus.SUCCEEDED else None,
                    raw_request={"payment_method": "pay_on_receipt", "source": "dashboard"},
                )
            else:
                payment.provider = Payment.Provider.MANUAL
                payment.status = next_payment_status
                payment.amount = order.total_amount
                payment.currency = order.currency
                if next_payment_status == Order.PaymentStatus.SUCCEEDED:
                    payment.paid_at = now
                elif next_payment_status in self.RESET_PAID_AT_STATUSES:
                    payment.paid_at = None
                PaymentWorkflowService.save_payment(
                    payment,
                    update_fields=[
                        "provider",
                        "status",
                        "amount",
                        "currency",
                        "paid_at",
                        "updated_at",
                    ],
                )

            if next_payment_status == Order.PaymentStatus.SUCCEEDED:
                if order.paid_at is None:
                    order.paid_at = payment.paid_at or now
                    order.save(update_fields=["paid_at", "updated_at"])
            elif next_payment_status in self.RESET_PAID_AT_STATUSES and order.paid_at is not None:
                order.paid_at = None
                order.save(update_fields=["paid_at", "updated_at"])

            order.refresh_from_db()
            OrderStatusTransition.log_if_changed(
                order=order,
                transition_type=OrderStatusTransition.TransitionType.PAYMENT_STATUS,
                from_value=previous_payment_status,
                to_value=order.payment_status,
                changed_by=actor,
            )
            if (
                previous_payment_status != Order.PaymentStatus.SUCCEEDED
                and order.payment_status == Order.PaymentStatus.SUCCEEDED
            ):
                OrderNotificationService.schedule_paid(order.id)
            return order
