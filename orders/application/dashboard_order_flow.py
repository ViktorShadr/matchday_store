import logging
from dataclasses import dataclass

from django.db import transaction

from orders.application.order_notification_service import OrderNotificationService
from orders.models import Order, OrderStatusTransition
from orders.services import (
    ManualPaymentUpdateError,
    ManualPaymentUpdateService,
    OrderCancellationError,
    OrderCancellationService,
    OrderIssueError,
    OrderIssueService,
)
from store.presenters import DashboardOrderPresenter

audit_logger = logging.getLogger("audit")


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
        issue_service: OrderIssueService | None = None,
    ):
        self.cancellation_service = cancellation_service or OrderCancellationService()
        self.payment_service = payment_service or ManualPaymentUpdateService()
        self.issue_service = issue_service or OrderIssueService()

    @staticmethod
    def validate_status_key(next_status: str) -> bool:
        return next_status in DashboardOrderPresenter.STATUS_META

    @staticmethod
    def validate_payment_status_key(next_payment_status: str) -> bool:
        return next_payment_status in {choice[0] for choice in DashboardOrderPresenter.PAYMENT_STATUS_CHOICES}

    def update_order_status(
        self,
        order: Order,
        next_status: str,
        actor=None,
    ) -> DashboardOrderStatusUpdateResult:
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
                    cancelled_order = self.cancellation_service.cancel_order(order_id=order.pk, actor=actor)
                except OrderCancellationError as exc:
                    raise DashboardOrderFlowError(str(exc)) from exc
                OrderStatusTransition.log_if_changed(
                    order=cancelled_order,
                    transition_type=OrderStatusTransition.TransitionType.DASHBOARD_STATUS,
                    from_value=current_status,
                    to_value=next_status,
                    changed_by=actor,
                )
                audit_logger.info(
                    "Статус заказа изменен через dashboard",
                    extra={
                        "event": "dashboard_order_status_changed",
                        "order_id": cancelled_order.id,
                        "from_status": current_status,
                        "to_status": next_status,
                        "actor_id": getattr(actor, "id", None),
                    },
                )
                return DashboardOrderStatusUpdateResult(
                    order=cancelled_order,
                    changed=True,
                    message="Заказ отменен.",
                )

            if next_status == "issued" and order.payment_status != Order.PaymentStatus.SUCCEEDED:
                raise DashboardOrderFlowError("Нельзя выдать заказ без подтвержденной оплаты.")

            previous_order_status = order.status
            previous_fulfillment_status = order.fulfillment_status
            if next_status == "issued":
                try:
                    self.issue_service.consume_reserved_stock(order_id=order.pk)
                except OrderIssueError as exc:
                    raise DashboardOrderFlowError(str(exc)) from exc

            DashboardOrderPresenter.apply_status(order, next_status)
            order.save(update_fields=["fulfillment_status", "status", "issued_at", "cancelled_at", "updated_at"])
            OrderStatusTransition.log_if_changed(
                order=order,
                transition_type=OrderStatusTransition.TransitionType.DASHBOARD_STATUS,
                from_value=current_status,
                to_value=next_status,
                changed_by=actor,
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
            audit_logger.info(
                "Статус заказа изменен через dashboard",
                extra={
                    "event": "dashboard_order_status_changed",
                    "order_id": order.id,
                    "from_status": current_status,
                    "to_status": next_status,
                    "actor_id": getattr(actor, "id", None),
                },
            )
            if next_status == "ready":
                OrderNotificationService.schedule_ready(order.id)
            return DashboardOrderStatusUpdateResult(order=order, changed=True, message="Статус заказа обновлен.")

    def update_payment_status(
        self,
        order: Order,
        next_payment_status: str,
        actor=None,
    ) -> DashboardPaymentStatusUpdateResult:
        if not self.validate_payment_status_key(next_payment_status):
            raise DashboardOrderFlowError("Недопустимый статус оплаты.")

        try:
            updated_order = self.payment_service.update_order_payment_status(
                order_id=order.pk,
                next_payment_status=next_payment_status,
                actor=actor,
            )
        except ManualPaymentUpdateError as exc:
            raise DashboardOrderFlowError(str(exc)) from exc

        audit_logger.info(
            "Статус оплаты заказа изменен через dashboard",
            extra={
                "event": "dashboard_payment_status_changed",
                "order_id": updated_order.id,
                "payment_status": next_payment_status,
                "actor_id": getattr(actor, "id", None),
            },
        )

        return DashboardPaymentStatusUpdateResult(
            order=updated_order,
            changed=True,
            message="Статус оплаты обновлен.",
        )
