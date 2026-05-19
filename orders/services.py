import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

from orders.application.checkout_context import CheckoutContext
from orders.application.order_notification_service import OrderNotificationService
from orders.models import Order, OrderItem, OrderStatusTransition
from orders.repositories import IOrderRepository, IPaymentRepository, OrderRepository, PaymentRepository
from payments.application import PaymentWorkflowService
from payments.models import Payment
from store.models import ProductVariant
from store.repositories import IProductVariantRepository, ProductVariantRepository
from store.services.cart_service import CartService
from store.services.interfaces import ICheckoutService

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


class CheckoutError(Exception):
    """Бизнес-ошибка оформления заказа."""


class OrderCancellationError(Exception):
    """Бизнес-ошибка отмены заказа."""


class OrderIssueError(Exception):
    """Бизнес-ошибка выдачи заказа."""


class ManualPaymentUpdateError(Exception):
    """Бизнес-ошибка обновления оплаты заказа."""


@dataclass(slots=True)
class CheckoutOrderLines:
    subtotal_amount: Decimal
    order_items: list[OrderItem]
    processable_cart_items: list
    skipped_cart_item_ids: list[int]


class OrderStockReservationService:
    """Доменный сервис резервирования и списания складских остатков."""

    @staticmethod
    def reserve_variant(variant: ProductVariant, quantity: int) -> None:
        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            quantity__gte=F("reserved_quantity") + quantity,
        ).update(
            reserved_quantity=F("reserved_quantity") + quantity,
            updated_at=timezone.now(),
        )
        if updated != 1:
            logger.warning(
                "checkout.stock_reservation_failed",
                extra={
                    "event": "checkout.stock_reservation_failed",
                    "product_variant_id": variant.pk,
                    "requested_quantity": quantity,
                    "available_quantity": variant.available_quantity,
                },
            )
            raise CheckoutError(
                f'Недостаточно товара "{variant.product.name}" на складе. '
                f"Доступно: {variant.available_quantity} шт."
            )
        variant.reserved_quantity += quantity

    @staticmethod
    def release_variant_reservation(variant: ProductVariant, quantity: int) -> None:
        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            reserved_quantity__gte=quantity,
        ).update(
            reserved_quantity=F("reserved_quantity") - quantity,
            updated_at=timezone.now(),
        )
        if updated != 1:
            raise OrderCancellationError(
                f'Невозможно снять резерв по товару "{variant.product.name}": '
                "зарезервировано меньше, чем требуется для отмены."
            )
        variant.reserved_quantity -= quantity

    @staticmethod
    def issue_variant(variant: ProductVariant, quantity: int) -> None:
        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            quantity__gte=quantity,
            reserved_quantity__gte=quantity,
        ).update(
            quantity=F("quantity") - quantity,
            reserved_quantity=F("reserved_quantity") - quantity,
            updated_at=timezone.now(),
        )
        if updated != 1:
            raise OrderIssueError(
                f'Невозможно выдать товар "{variant.product.name}": '
                "физический остаток или резерв меньше количества в заказе."
            )
        variant.quantity -= quantity
        variant.reserved_quantity -= quantity


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
    def _get_cart_id(cart) -> Optional[int]:
        """Безопасно извлечь cart id (в т.ч. для тестовых/fake объектов)."""
        return getattr(cart, "id", None)

    @staticmethod
    def build_checkout_idempotency_key(
        checkout_token: Optional[str],
        user_id: Optional[int] = None,
        session_key: Optional[str] = None,
    ) -> str:
        """Собрать idempotency key для checkout с учетом пользователя или гостевой сессии."""
        if checkout_token:
            if user_id is not None:
                return f"checkout-{user_id}-{checkout_token}"
            if session_key:
                return f"checkout-session-{session_key}-{checkout_token}"
            return f"checkout-{checkout_token}"
        return uuid4().hex

    def _find_existing_checkout_payment(
        self,
        checkout_token: Optional[str],
        user_id: Optional[int],
        session_key: Optional[str] = None,
    ):
        """Найти уже созданный payment для checkout (новый и legacy ключи)."""
        if not checkout_token:
            return None

        lookup_keys = [
            self.build_checkout_idempotency_key(
                checkout_token,
                user_id=user_id,
                session_key=session_key,
            )
        ]

        # Backward compatibility for keys created before user-scoped idempotency.
        legacy_key = self.build_checkout_idempotency_key(checkout_token)
        if legacy_key not in lookup_keys:
            lookup_keys.append(legacy_key)

        for lookup_key in lookup_keys:
            existing_payment = self.payment_repository.get_payment_by_idempotency_key(lookup_key)
            if existing_payment and existing_payment.order.user_id == user_id:
                return existing_payment

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
        if user_id is None:
            return

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
    def _lock_checkout_user(user_id: int):
        return get_user_model().objects.select_for_update().only("id").get(pk=user_id)

    @staticmethod
    def _ensure_stock_reserve_mode_enabled() -> None:
        if getattr(settings, "STOCK_RESERVE_MODE_ENABLED", True):
            return
        raise CheckoutError("Оформление заказов временно недоступно. Повторите попытку позже.")

    @staticmethod
    def _lock_cart_items(cart):
        return list(cart.items.select_related("product_variant__product").select_for_update().order_by("pk"))

    def _lock_variants_for_cart_items(self, cart_items):
        locked_variant_ids = [item.product_variant_id for item in cart_items]
        return {
            variant.id: variant
            for variant in self.product_variant_repository.get_variants_for_update(locked_variant_ids)
        }

    def _build_order_lines(self, cart_items, locked_variants: dict[int, ProductVariant]) -> CheckoutOrderLines:
        subtotal_amount = Decimal("0.00")
        order_items = []
        processable_cart_items = []
        skipped_cart_item_ids = []

        for cart_item in cart_items:
            variant = locked_variants.get(cart_item.product_variant_id)
            if variant is None:
                skipped_cart_item_ids.append(cart_item.pk)
                continue

            available_quantity = variant.available_quantity

            # Позиции, которые нельзя оформить (сняты с продажи или нулевой доступный остаток),
            # исключаем из checkout и удаляем из корзины в этой же транзакции.
            if not variant.product.is_on_sale or available_quantity <= 0:
                skipped_cart_item_ids.append(cart_item.pk)
                continue

            self._ensure_sku_quantity_limit(cart_item, variant)

            if available_quantity < cart_item.quantity:
                logger.warning(
                    "checkout.stock_reservation_failed",
                    extra={
                        "event": "checkout.stock_reservation_failed",
                        "product_variant_id": variant.id,
                        "requested_quantity": cart_item.quantity,
                        "available_quantity": available_quantity,
                    },
                )
                raise CheckoutError(
                    f'Недостаточно товара "{variant.product.name}" на складе. ' f"Доступно: {available_quantity} шт."
                )

            if variant.price <= 0:
                raise CheckoutError(
                    f'Некорректная цена для товара "{variant.product.name}". ' "Обратитесь в поддержку."
                )

            line_total = variant.price * cart_item.quantity
            subtotal_amount += line_total
            order_items.append(
                OrderItem(
                    product_variant=variant,
                    product_name_snapshot=variant.product.name,
                    sku_snapshot=variant.sku or str(variant.id),
                    size_snapshot=self._normalize_snapshot_text(variant.size),
                    color_snapshot=self._normalize_snapshot_text(variant.color),
                    unit_price=variant.price,
                    quantity=cart_item.quantity,
                    line_total=line_total,
                )
            )
            processable_cart_items.append(cart_item)

        return CheckoutOrderLines(
            subtotal_amount=subtotal_amount,
            order_items=order_items,
            processable_cart_items=processable_cart_items,
            skipped_cart_item_ids=skipped_cart_item_ids,
        )

    def _create_order(
        self,
        checkout_context: CheckoutContext,
        cleaned_data,
        cart,
        subtotal_amount: Decimal,
        *,
        user=None,
    ) -> Order:
        return self.order_repository.create_order(
            number=self.build_order_number(),
            user=user if user is not None else checkout_context.user_for_order,
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
            source_cart_id=self._get_cart_id(cart),
            confirmed_at=timezone.now(),
        )

    def _create_order_items(self, order: Order, order_items: list[OrderItem]) -> None:
        for item in order_items:
            item.order = order
        self.order_repository.bulk_create_order_items(order_items)

    @staticmethod
    def _create_manual_payment(order: Order, amount: Decimal, payment_idempotency_key: str) -> Payment:
        return PaymentWorkflowService.create_payment(
            order=order,
            provider=Payment.Provider.MANUAL,
            idempotency_key=payment_idempotency_key,
            status=Payment.Status.PENDING,
            amount=amount,
            currency=order.currency,
            raw_request={
                "payment_method": "pay_on_receipt",
                "pickup_location_code": settings.STORE_PICKUP_LOCATION_CODE,
            },
        )

    @staticmethod
    def _reserve_stock(processable_cart_items, locked_variants: dict[int, ProductVariant]) -> None:
        for cart_item in processable_cart_items:
            variant = locked_variants[cart_item.product_variant_id]
            OrderStockReservationService.reserve_variant(variant, cart_item.quantity)

    @staticmethod
    def _cleanup_cart(cart, cart_item_ids: list[int]) -> None:
        if cart_item_ids:
            cart.items.filter(pk__in=cart_item_ids).delete()

    @staticmethod
    def _schedule_notifications_on_commit(order: Order) -> None:
        OrderNotificationService.schedule_created(order.id)

    @staticmethod
    def _log_checkout_started(checkout_context: CheckoutContext) -> None:
        logger.info(
            "checkout.started",
            extra={
                "event": "checkout.started",
                "user_id": checkout_context.user_id,
                "cart_id": CheckoutService._get_cart_id(checkout_context.cart_context.cart),
            },
        )

    @staticmethod
    def _log_checkout_idempotency_conflict(checkout_context: CheckoutContext, order_id: int) -> None:
        logger.info(
            "checkout.idempotency_conflict",
            extra={
                "event": "checkout.idempotency_conflict",
                "order_id": order_id,
                "user_id": checkout_context.user_id,
            },
        )

    def create_order_from_cart(
        self,
        checkout_context: CheckoutContext,
        cleaned_data,
        checkout_token: Optional[str] = None,
    ):
        """Создать заказ, зарезервировать остатки и очистить корзину."""
        self._log_checkout_started(checkout_context)
        payment_idempotency_key = self.build_checkout_idempotency_key(
            checkout_token,
            user_id=checkout_context.user_id,
            session_key=checkout_context.session_key,
        )

        existing_payment = self._find_existing_checkout_payment(
            checkout_token,
            checkout_context.user_id,
            checkout_context.session_key,
        )
        if existing_payment:
            self._log_checkout_idempotency_conflict(checkout_context, existing_payment.order_id)
            return existing_payment.order

        self._ensure_stock_reserve_mode_enabled()
        self._ensure_active_order_limit(checkout_context.user_id)

        order = None
        unavailable_only_error = None

        try:
            with transaction.atomic():
                locked_user = None
                if checkout_context.user_id is not None:
                    locked_user = self._lock_checkout_user(checkout_context.user_id)

                existing_payment = self._find_existing_checkout_payment(
                    checkout_token,
                    checkout_context.user_id,
                    checkout_context.session_key,
                )
                if existing_payment:
                    self._log_checkout_idempotency_conflict(checkout_context, existing_payment.order_id)
                    return existing_payment.order
                self._ensure_stock_reserve_mode_enabled()
                self._ensure_active_order_limit(checkout_context.user_id)

                cart = checkout_context.cart_context.cart
                cart_items = self._lock_cart_items(cart)

                if not cart_items:
                    if checkout_token:
                        # Повторно проверяем idempotency после захвата блокировок:
                        # в параллельном submit первый запрос мог уже создать заказ и очистить корзину.
                        existing_payment = self._find_existing_checkout_payment(
                            checkout_token,
                            checkout_context.user_id,
                            checkout_context.session_key,
                        )
                        if existing_payment:
                            self._log_checkout_idempotency_conflict(checkout_context, existing_payment.order_id)
                            return existing_payment.order
                    raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")

                locked_variants = self._lock_variants_for_cart_items(cart_items)
                order_lines = self._build_order_lines(cart_items, locked_variants)
                self._cleanup_cart(cart, order_lines.skipped_cart_item_ids)

                if not order_lines.order_items:
                    unavailable_only_error = "В корзине не осталось доступных товаров. " "Недоступные позиции удалены."
                else:
                    order = self._create_order(
                        checkout_context,
                        cleaned_data,
                        cart,
                        order_lines.subtotal_amount,
                        user=locked_user,
                    )
                    self._create_order_items(order, order_lines.order_items)
                    self._create_manual_payment(order, order_lines.subtotal_amount, payment_idempotency_key)
                    self._reserve_stock(order_lines.processable_cart_items, locked_variants)
                    self._cleanup_cart(cart, [item.pk for item in order_lines.processable_cart_items])
                    self._schedule_notifications_on_commit(order)
        except CheckoutError as exc:
            logger.warning(
                "checkout.failed",
                extra={
                    "event": "checkout.failed",
                    "user_id": checkout_context.user_id,
                    "cart_id": self._get_cart_id(checkout_context.cart_context.cart),
                    "reason": str(exc),
                },
            )
            raise
        except IntegrityError as exc:
            if checkout_token:
                existing_payment = self._find_existing_checkout_payment(
                    checkout_token,
                    checkout_context.user_id,
                    checkout_context.session_key,
                )
                if existing_payment:
                    self._log_checkout_idempotency_conflict(checkout_context, existing_payment.order_id)
                    return existing_payment.order
            logger.warning(
                "checkout.idempotency_conflict",
                extra={
                    "event": "checkout.idempotency_conflict",
                    "user_id": checkout_context.user_id,
                    "cart_id": self._get_cart_id(checkout_context.cart_context.cart),
                    "reason": "integrity_error",
                },
            )
            raise CheckoutError("Заказ уже обрабатывается. Обновите страницу и проверьте статус заказа.") from exc

        if order:
            logger.info(
                "order.created",
                extra={
                    "event": "order.created",
                    "order_id": order.id,
                    "user_id": order.user_id,
                },
            )
            audit_logger.info(
                "order.created",
                extra={
                    "event": "order.created",
                    "order_id": order.id,
                    "user_id": order.user_id,
                },
            )
            return order

        if unavailable_only_error:
            logger.warning(
                "checkout.failed",
                extra={
                    "event": "checkout.failed",
                    "user_id": checkout_context.user_id,
                    "cart_id": self._get_cart_id(checkout_context.cart_context.cart),
                    "reason": unavailable_only_error,
                },
            )
            raise CheckoutError(unavailable_only_error)

        logger.warning(
            "checkout.failed",
            extra={
                "event": "checkout.failed",
                "user_id": checkout_context.user_id,
                "cart_id": self._get_cart_id(checkout_context.cart_context.cart),
                "reason": "empty_cart",
            },
        )
        raise CheckoutError("Корзина пуста. Добавьте товары перед оформлением заказа.")


class OrderCancellationService:
    """Сервис безопасной отмены заказа со снятием складского резерва."""

    CANCELLABLE_ORDER_STATUSES = frozenset(
        {
            Order.Status.PLACED,
            Order.Status.AWAITING_PAYMENT,
            Order.Status.PROCESSING,
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

    @staticmethod
    def _cancel_manual_payments(order: Order) -> None:
        manual_payments = list(
            Payment.objects.select_for_update().filter(order=order, provider=Payment.Provider.MANUAL).order_by("pk")
        )
        payments_to_update = []
        now = timezone.now()
        for payment in manual_payments:
            if payment.status == Payment.Status.CANCELLED and payment.paid_at is None:
                continue
            payment.status = Payment.Status.CANCELLED
            payment.paid_at = None
            payment.updated_at = now
            payments_to_update.append(payment)

        if payments_to_update:
            Payment.objects.bulk_update(payments_to_update, ["status", "paid_at", "updated_at"])

    @classmethod
    def _ensure_order_can_be_cancelled(cls, order: Order) -> None:
        if order.status not in cls.CANCELLABLE_ORDER_STATUSES:
            raise OrderCancellationError(f'Заказ в статусе "{order.get_status_display()}" нельзя отменить.')

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
        Отменить заказ и снять складской резерв.

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
                self._cancel_manual_payments(order)
                logger.info(
                    "order.cancel_already_applied",
                    extra={
                        "event": "order.cancel_already_applied",
                        "order_id": order.id,
                        "user_id": order.user_id,
                        "actor_id": getattr(actor, "id", None),
                    },
                )
                return order

            self._ensure_order_can_be_cancelled(order)

            order_items = list(order.items.select_related("product_variant").order_by("pk"))
            variant_ids = sorted({item.product_variant_id for item in order_items if item.product_variant_id})
            locked_variants = {
                variant.id: variant for variant in self.product_variant_repository.get_variants_for_update(variant_ids)
            }
            released_items_count = 0

            for order_item in order_items:
                if not order_item.product_variant_id:
                    continue

                variant = locked_variants.get(order_item.product_variant_id)
                if variant is None:
                    continue

                OrderStockReservationService.release_variant_reservation(variant, order_item.quantity)
                released_items_count += order_item.quantity

            self._cancel_manual_payments(order)

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
            logger.info(
                "order.cancelled",
                extra={
                    "event": "order.cancelled",
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "actor_id": getattr(actor, "id", None),
                    "from_order_status": previous_order_status,
                    "to_order_status": order.status,
                    "from_fulfillment_status": previous_fulfillment_status,
                    "to_fulfillment_status": order.fulfillment_status,
                    "from_payment_status": previous_payment_status,
                    "to_payment_status": order.payment_status,
                },
            )
            audit_logger.info(
                "order.cancelled",
                extra={
                    "event": "order.cancelled",
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "actor_id": getattr(actor, "id", None),
                },
            )
            logger.info(
                "checkout.stock_reservation_released",
                extra={
                    "event": "checkout.stock_reservation_released",
                    "order_id": order.id,
                    "released_items_count": released_items_count,
                },
            )

            return order


class OrderIssueService:
    """Сервис списания физического склада при фактической выдаче заказа."""

    ISSUABLE_ORDER_STATUSES = frozenset({Order.Status.PROCESSING})
    ISSUABLE_FULFILLMENT_STATUSES = frozenset({Order.FulfillmentStatus.RESERVED})
    ISSUABLE_PAYMENT_STATUSES = frozenset({Order.PaymentStatus.SUCCEEDED})

    def __init__(self, product_variant_repository: Optional[IProductVariantRepository] = None):
        self.product_variant_repository = product_variant_repository or ProductVariantRepository()

    @staticmethod
    def _is_already_issued(order: Order) -> bool:
        return order.status == Order.Status.DELIVERED and order.fulfillment_status == Order.FulfillmentStatus.DELIVERED

    @classmethod
    def _ensure_order_can_be_issued(cls, order: Order) -> None:
        if cls._is_already_issued(order):
            return

        if order.status not in cls.ISSUABLE_ORDER_STATUSES:
            raise OrderIssueError(f'Заказ в статусе "{order.get_status_display()}" нельзя выдать.')

        if order.fulfillment_status not in cls.ISSUABLE_FULFILLMENT_STATUSES:
            raise OrderIssueError(
                f'Заказ в статусе исполнения "{order.get_fulfillment_status_display()}" нельзя выдать.'
            )

        if order.payment_status not in cls.ISSUABLE_PAYMENT_STATUSES:
            raise OrderIssueError("Нельзя выдать заказ без подтвержденной оплаты.")

    def consume_reserved_stock(self, order_id: int) -> Order:
        """Списать физический склад и резерв по всем позициям заказа."""
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist as exc:
                raise OrderIssueError("Заказ не найден.") from exc

            if self._is_already_issued(order):
                return order

            self._ensure_order_can_be_issued(order)

            order_items = list(order.items.select_related("product_variant").order_by("pk"))
            variant_ids = sorted({item.product_variant_id for item in order_items if item.product_variant_id})
            locked_variants = {
                variant.id: variant for variant in self.product_variant_repository.get_variants_for_update(variant_ids)
            }
            issued_items_count = 0

            for order_item in order_items:
                if not order_item.product_variant_id:
                    continue

                variant = locked_variants.get(order_item.product_variant_id)
                if variant is None:
                    raise OrderIssueError(f"Товар из позиции заказа {order_item.pk} не найден на складе.")

                OrderStockReservationService.issue_variant(variant, order_item.quantity)
                issued_items_count += order_item.quantity

            logger.info(
                "order.stock_issued",
                extra={
                    "event": "order.stock_issued",
                    "order_id": order.id,
                    "issued_items_count": issued_items_count,
                },
            )

            return order


def add_business_days(value, business_days: int):
    """Return a local-time datetime after adding Monday-Friday business days."""
    deadline = timezone.localtime(value) if timezone.is_aware(value) else timezone.make_aware(value)
    if business_days <= 0:
        return deadline

    remaining_days = business_days
    while remaining_days > 0:
        deadline += timedelta(days=1)
        if deadline.weekday() < 5:
            remaining_days -= 1
    return deadline


class OrderAutoCancellationService:
    """Auto-cancel expired pickup orders without direct stock mutations."""

    ELIGIBLE_ORDER_STATUSES = OrderCancellationService.CANCELLABLE_ORDER_STATUSES
    ELIGIBLE_FULFILLMENT_STATUSES = OrderCancellationService.CANCELLABLE_FULFILLMENT_STATUSES
    NON_CANCELLABLE_PAYMENT_STATUSES = OrderCancellationService.NON_CANCELLABLE_PAYMENT_STATUSES

    def __init__(self, cancellation_service: Optional[OrderCancellationService] = None):
        self.cancellation_service = cancellation_service or OrderCancellationService()

    @staticmethod
    def get_order_retention_started_at(order: Order):
        return order.confirmed_at or order.created_at

    @classmethod
    def get_pickup_deadline(cls, order: Order, *, business_days: Optional[int] = None):
        retention_business_days = (
            settings.ORDER_PICKUP_RETENTION_BUSINESS_DAYS if business_days is None else business_days
        )
        return add_business_days(cls.get_order_retention_started_at(order), retention_business_days)

    @classmethod
    def is_pickup_deadline_expired(cls, order: Order, *, now=None, business_days: Optional[int] = None) -> bool:
        current_time = timezone.localtime(now or timezone.now())
        return current_time >= cls.get_pickup_deadline(order, business_days=business_days)

    def cancel_expired_pickup_orders(
        self,
        *,
        now=None,
        business_days: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> dict[str, int]:
        current_time = now or timezone.now()
        retention_business_days = (
            settings.ORDER_PICKUP_RETENTION_BUSINESS_DAYS if business_days is None else business_days
        )
        max_orders = settings.ORDER_AUTO_CANCEL_BATCH_SIZE if batch_size is None else batch_size
        rough_cutoff = current_time - timedelta(days=max(retention_business_days, 0))

        candidate_orders = list(
            Order.objects.filter(
                delivery_method=Order.DeliveryMethod.PICKUP,
                status__in=self.ELIGIBLE_ORDER_STATUSES,
                fulfillment_status__in=self.ELIGIBLE_FULFILLMENT_STATUSES,
            )
            .annotate(retention_started_at=Coalesce("confirmed_at", "created_at"))
            .filter(retention_started_at__lte=rough_cutoff)
            .exclude(payment_status__in=self.NON_CANCELLABLE_PAYMENT_STATUSES)
            .order_by("retention_started_at", "pk")[:max_orders]
        )

        result = {
            "scanned": len(candidate_orders),
            "cancelled": 0,
            "skipped": 0,
            "failed": 0,
        }
        for order in candidate_orders:
            if not self.is_pickup_deadline_expired(order, now=current_time, business_days=retention_business_days):
                result["skipped"] += 1
                continue

            try:
                self.cancellation_service.cancel_order(order_id=order.pk)
            except OrderCancellationError as exc:
                result["failed"] += 1
                logger.warning(
                    "order.auto_cancel_failed",
                    extra={
                        "event": "order.auto_cancel_failed",
                        "order_id": order.id,
                        "reason": str(exc),
                    },
                )
            else:
                result["cancelled"] += 1

        if result["scanned"] > 0:
            logger.info(
                "order.auto_cancel_completed",
                extra={
                    "event": "order.auto_cancel_completed",
                    "scanned": result["scanned"],
                    "cancelled": result["cancelled"],
                    "skipped": result["skipped"],
                    "failed": result["failed"],
                },
            )

        return result


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
            logger.info(
                "order.payment_status_updated",
                extra={
                    "event": "order.payment_status_updated",
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "actor_id": getattr(actor, "id", None),
                    "from_payment_status": previous_payment_status,
                    "to_payment_status": order.payment_status,
                },
            )
            if (
                previous_payment_status != Order.PaymentStatus.SUCCEEDED
                and order.payment_status == Order.PaymentStatus.SUCCEEDED
            ):
                OrderNotificationService.schedule_paid(order.id)
            return order
