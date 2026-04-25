from dataclasses import dataclass

from django.db import transaction

from orders.models import Order
from orders.application.order_notification_service import OrderNotificationService
from orders.services import (
    ManualPaymentUpdateError,
    ManualPaymentUpdateService,
    OrderCancellationError,
    OrderCancellationService,
)
from store.presenters import DashboardOrderPresenter


class DashboardOrderFlowError(Exception):
    """Ошибка staff-flow изменения статуса заказа."""


@dataclass(slots=True)
class DashboardOrderStatusUpdateResult:
    order: Order
    changed: bool = False
    message: str = ""


@dataclass(slots=True)
class DashboardPaymentStatusUpdateResult:
    order: Order
    changed: bool = False
    message: str = ""


class DashboardOrderFlowService:
    """Application-слой для staff-операций над заказом из dashboard."""

    def __init__(
        self,
        cancellation_service: OrderCancellationService | None = None,
        payment_service: ManualPaymentUpdateService | None = None,
    ):
        self.cancellation_service = cancellation_service or OrderCancellationService()
        self.payment_service = payment_service or ManualPaymentUpdateService()

    @staticmethod
    def validate_status_key(next_status: str) -> bool:
        return next_status in DashboardOrderPresenter.STATUS_META

    @staticmethod
    def validate_payment_status_key(next_payment_status: str) -> bool:
        return next_payment_status in {choice[0] for choice in DashboardOrderPresenter.PAYMENT_STATUS_CHOICES}

    def update_order_status(self, order: Order, next_status: str) -> DashboardOrderStatusUpdateResult:
        if not self.validate_status_key(next_status):
            raise DashboardOrderFlowError("Недопустимый статус заказа.")

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order.pk)
            except Order.DoesNotExist as exc:
                raise DashboardOrderFlowError("Заказ не найден.") from exc

            current_status = DashboardOrderPresenter.get_status_key(order)

            if current_status in DashboardOrderPresenter.FINAL_STATUS_KEYS and next_status != current_status:
                raise DashboardOrderFlowError("Нельзя изменить заказ после отмены или выдачи.")

            allowed_transitions = DashboardOrderPresenter.STATUS_TRANSITIONS[current_status]
            if next_status not in allowed_transitions:
                raise DashboardOrderFlowError("Недопустимый переход статуса для текущего состояния заказа.")

            if next_status == current_status:
                return DashboardOrderStatusUpdateResult(
                    order=order,
                    changed=False,
                    message="Статус заказа уже установлен.",
                )

            if next_status == "cancelled":
                try:
                    cancelled_order = self.cancellation_service.cancel_order(order_id=order.pk)
                except OrderCancellationError as exc:
                    raise DashboardOrderFlowError(str(exc)) from exc
                return DashboardOrderStatusUpdateResult(
                    order=cancelled_order,
                    changed=True,
                    message="Заказ отменен.",
                )

            if next_status == "issued" and order.payment_status != Order.PaymentStatus.SUCCEEDED:
                raise DashboardOrderFlowError("Нельзя выдать заказ без подтвержденной оплаты.")

            DashboardOrderPresenter.apply_status(order, next_status)
            order.save(update_fields=["fulfillment_status", "status", "cancelled_at", "updated_at"])
            if next_status == "ready":
                OrderNotificationService.schedule_ready(order.id)
            return DashboardOrderStatusUpdateResult(order=order, changed=True, message="Статус заказа обновлен.")

    def update_payment_status(self, order: Order, next_payment_status: str) -> DashboardPaymentStatusUpdateResult:
        if not self.validate_payment_status_key(next_payment_status):
            raise DashboardOrderFlowError("Недопустимый статус оплаты.")

        try:
            updated_order = self.payment_service.update_order_payment_status(
                order_id=order.pk,
                next_payment_status=next_payment_status,
            )
        except ManualPaymentUpdateError as exc:
            raise DashboardOrderFlowError(str(exc)) from exc

        return DashboardPaymentStatusUpdateResult(
            order=updated_order,
            changed=True,
            message="Статус оплаты обновлен.",
        )
