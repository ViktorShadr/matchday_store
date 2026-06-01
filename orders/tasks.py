import logging
import re
from email.utils import parseaddr

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from config.email_delivery import (
    EMAIL_TASK_AUTORETRY_KWARGS,
    NotificationDeliveryError,
    build_email_delivery_log_extra,
    is_permanent_email_delivery_error,
)
from orders.models import Order
from store.site_contacts import format_business_days_label

logger = logging.getLogger(__name__)
STAFF_NEW_ORDER_EVENT_KEY = "staff_created"
EMAIL_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _log_notification_error(
    order_id: int,
    event_key: str,
    reason: str,
    *,
    with_traceback: bool = False,
    error_type: str | None = None,
    task=None,
    retries: int | None = None,
) -> None:
    base_event_name = (
        "order.staff_notification_send_failed"
        if event_key == STAFF_NEW_ORDER_EVENT_KEY
        else "order.notification_send_failed"
    )
    if reason == "smtp_permanent_failure":
        event_name = f"{base_event_name}.permanent"
    elif reason in {"send_mail_failed", "send_mail_returned_zero"}:
        event_name = f"{base_event_name}.transient"
    elif reason in {"invalid_default_from_email", "unsupported_event_key"}:
        event_name = f"{base_event_name}.configuration"
    else:
        event_name = base_event_name
    extra = build_email_delivery_log_extra(
        task=task,
        retries=retries,
        event=event_name,
        reason=reason,
        error_type=error_type,
        order_id=order_id,
        event_key=event_key,
    )
    if with_traceback:
        logger.exception(event_name, extra=extra)
        return
    logger.error(event_name, extra=extra)


def _build_order_detail_url(order: Order) -> str:
    return f"{settings.SITE_URL}{reverse('users:order_detail', kwargs={'pk': order.pk})}"


def _build_guest_order_manage_url(order: Order) -> str:
    from orders.services import GuestOrderAccessTokenService

    issued_token = GuestOrderAccessTokenService.issue_token_for_email(order)
    return f"{settings.SITE_URL}{reverse('orders:guest_order_detail', kwargs={'token': issued_token.raw_token})}"


def _build_dashboard_order_detail_url(order: Order) -> str:
    return f"{settings.SITE_URL}{reverse('store:dashboard_order_detail', kwargs={'pk': order.pk})}"


def _resolve_support_email_for_notifications() -> str:
    configured_value = (getattr(settings, "STORE_SUPPORT_EMAIL", "") or "").strip()
    if not configured_value:
        return (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()

    _, parsed_email = parseaddr(configured_value)
    if parsed_email and "@" in parsed_email:
        return parsed_email.strip()

    match = EMAIL_ADDRESS_RE.search(configured_value)
    if match:
        return match.group(0)

    return configured_value


def _build_order_notification_base_lines(order: Order, event_key: str) -> list[str]:
    base_lines = [
        f"Заказ: {order.number or order.pk}",
        f"Сумма: {order.total_amount} {order.currency}",
    ]
    if order.user_id:
        base_lines.append(f"Детали заказа: {_build_order_detail_url(order)}")
        return base_lines

    base_lines.append("Сохраните номер заказа для связи с магазином.")
    if event_key == "created":
        guest_order_manage_url = _build_guest_order_manage_url(order)
        base_lines.append(f"Ссылка для просмотра и управления заказом: {guest_order_manage_url}")
        base_lines.append(
            "По этой ссылке можно посмотреть статус заказа или отменить заказ без регистрации. "
            "Не передавайте ссылку третьим лицам."
        )
        base_lines.append("После регистрации и подтверждения почты " "заказ появится в личном кабинете.")
    return base_lines


def _build_order_notification_content(order: Order, event_key: str) -> tuple[str, str]:
    order_number = order.number or str(order.pk)
    brand_name = settings.STORE_BRAND_NAME
    pickup_retention_label = format_business_days_label(settings.ORDER_PICKUP_RETENTION_BUSINESS_DAYS)
    base_lines = _build_order_notification_base_lines(order, event_key)

    if event_key == "created":
        subject = f"Заказ {order_number} принят"
        lines = [
            f"Спасибо за заказ в официальном магазине {brand_name}.",
            "Мы приняли ваш заказ и начали его обработку.",
            f"Самовывоз: {settings.STORE_PICKUP_LOCATION_NAME}",
            f"Адрес: {settings.STORE_PICKUP_ADDRESS}",
            f"Часы работы: {settings.STORE_PICKUP_HOURS}",
            "Оплата производится при получении.",
            f"Резерв хранится {pickup_retention_label}.",
            "Забрать заказ можно после уведомления о готовности.",
        ]
    elif event_key == "cancelled":
        subject = f"Заказ {order_number} отменен"
        lines = [
            "Ваш заказ отменен.",
            "Если отмена произошла по ошибке, оформите новый заказ или свяжитесь с нами.",
            f"Телефон магазина: {settings.STORE_PICKUP_PHONE}",
            f"Написать в поддержку: {_resolve_support_email_for_notifications()}",
        ]
    elif event_key == "ready":
        subject = f"Заказ {order_number} готов к выдаче"
        lines = [
            "Ваш заказ собран и готов к самовывозу.",
            f"Место выдачи: {settings.STORE_PICKUP_LOCATION_NAME}",
            f"Адрес: {settings.STORE_PICKUP_ADDRESS}",
            f"Часы работы: {settings.STORE_PICKUP_HOURS}",
        ]
    elif event_key == "paid":
        subject = f"Оплата по заказу {order_number} подтверждена"
        lines = [
            "Мы отметили оплату по вашему заказу.",
            "Если вы уже получили заказ, дополнительных действий не требуется.",
        ]
    else:
        raise ValueError(f"Unsupported order notification event: {event_key}")

    message = "\n".join([*lines, "", *base_lines])
    return subject, message


def _get_staff_order_notification_recipients() -> list[str]:
    raw_recipients = settings.STAFF_ORDER_NOTIFICATION_EMAILS
    if isinstance(raw_recipients, str):
        raw_recipients = raw_recipients.split(",")

    recipient_list = [email.strip() for email in raw_recipients if isinstance(email, str) and email.strip()]
    valid_recipient_list = [email for email in recipient_list if "@" in email]

    if len(valid_recipient_list) != len(recipient_list):
        logger.warning(
            "order.staff_notification_recipients_invalid",
            extra={
                "event": "order.staff_notification_recipients_invalid",
                "configured_recipient_count": len(recipient_list),
                "valid_recipient_count": len(valid_recipient_list),
            },
        )

    return valid_recipient_list


def _build_staff_order_items_lines(order: Order) -> list[str]:
    item_lines: list[str] = []
    for item in order.items.all():
        size = item.size_snapshot or "—"
        color = item.color_snapshot or "—"
        item_lines.append(
            f"- {item.product_name_snapshot} | размер: {size} | цвет: {color} | "
            f"{item.quantity} x {item.unit_price} {order.currency} = {item.line_total} {order.currency}"
        )

    if not item_lines:
        return ["- Позиции заказа не найдены"]
    return item_lines


def _build_staff_new_order_notification_content(order: Order) -> tuple[str, str]:
    order_number = order.number or str(order.pk)
    dashboard_url = _build_dashboard_order_detail_url(order)
    customer_comment = order.customer_comment.strip() if order.customer_comment else "—"

    lines = [
        f"Новый заказ в магазине {settings.STORE_BRAND_NAME}.",
        "",
        f"Номер заказа: {order_number}",
        f"Сумма заказа: {order.total_amount} {order.currency}",
        f"Статус заказа: {order.get_status_display()}",
        f"Статус оплаты: {order.get_payment_status_display()}",
        "",
        "Контакты клиента:",
        f"Получатель: {order.recipient_name or '—'}",
        f"Email: {order.email or '—'}",
        f"Телефон: {order.phone or '—'}",
        "",
        "Позиции заказа:",
        *_build_staff_order_items_lines(order),
        "",
        f"Комментарий клиента: {customer_comment}",
        "",
        f"Ссылка на заказ в dashboard: {dashboard_url}",
    ]

    subject = f"Новый заказ {order_number}"
    message = "\n".join(lines)
    return subject, message


def send_order_notification_sync(
    order_id: int,
    event_key: str,
    *,
    raise_on_error: bool = False,
    task=None,
    retries: int | None = None,
) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        _log_notification_error(order_id, event_key, "invalid_default_from_email", task=task, retries=retries)
        return False

    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning(
            "order.notification_skipped_order_not_found",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.notification_skipped_order_not_found",
                order_id=order_id,
                event_key=event_key,
            ),
        )
        return False

    if not order.email:
        logger.warning(
            "order.notification_skipped_recipient_missing",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.notification_skipped_recipient_missing",
                order_id=order_id,
                event_key=event_key,
            ),
        )
        return False

    try:
        subject, message = _build_order_notification_content(order, event_key)
    except ValueError:
        _log_notification_error(
            order_id,
            event_key,
            "unsupported_event_key",
            error_type="ValueError",
            task=task,
            retries=retries,
        )
        return False

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
        if sent_count == 0:
            _log_notification_error(order_id, event_key, "send_mail_returned_zero", task=task, retries=retries)
            if raise_on_error:
                raise NotificationDeliveryError("Не удалось отправить email-уведомление по заказу")
            return False
        logger.info(
            "order.notification_sent",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.notification_sent",
                order_id=order_id,
                event_key=event_key,
            ),
        )
        return True
    except NotificationDeliveryError:
        raise
    except Exception as exc:
        is_permanent_error = is_permanent_email_delivery_error(exc)
        _log_notification_error(
            order_id,
            event_key,
            "smtp_permanent_failure" if is_permanent_error else "send_mail_failed",
            with_traceback=True,
            error_type=exc.__class__.__name__,
            task=task,
            retries=retries,
        )
        if raise_on_error and not is_permanent_error:
            raise NotificationDeliveryError("Не удалось отправить email-уведомление по заказу") from exc
        return False


def send_staff_new_order_notification_sync(
    order_id: int,
    *,
    raise_on_error: bool = False,
    task=None,
    retries: int | None = None,
) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        _log_notification_error(
            order_id,
            STAFF_NEW_ORDER_EVENT_KEY,
            "invalid_default_from_email",
            task=task,
            retries=retries,
        )
        return False

    recipient_list = _get_staff_order_notification_recipients()
    if not recipient_list:
        logger.warning(
            "order.staff_notification_skipped_recipients_missing",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.staff_notification_skipped_recipients_missing",
                order_id=order_id,
                event_key=STAFF_NEW_ORDER_EVENT_KEY,
            ),
        )
        return False

    try:
        order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning(
            "order.staff_notification_skipped_order_not_found",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.staff_notification_skipped_order_not_found",
                order_id=order_id,
                event_key=STAFF_NEW_ORDER_EVENT_KEY,
            ),
        )
        return False

    subject, message = _build_staff_new_order_notification_content(order)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(
            "order.staff_notification_sent",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="order.staff_notification_sent",
                order_id=order_id,
                event_key=STAFF_NEW_ORDER_EVENT_KEY,
            ),
        )
        return True
    except Exception as exc:
        is_permanent_error = is_permanent_email_delivery_error(exc)
        _log_notification_error(
            order_id,
            STAFF_NEW_ORDER_EVENT_KEY,
            "smtp_permanent_failure" if is_permanent_error else "send_mail_failed",
            with_traceback=True,
            error_type=exc.__class__.__name__,
            task=task,
            retries=retries,
        )
        if raise_on_error and not is_permanent_error:
            raise NotificationDeliveryError("Не удалось отправить staff email-уведомление по заказу") from exc
        return False


@shared_task(**EMAIL_TASK_AUTORETRY_KWARGS)
def send_order_notification(self, order_id: int, event_key: str) -> bool:
    return send_order_notification_sync(order_id, event_key, raise_on_error=True, task=self)


@shared_task(**EMAIL_TASK_AUTORETRY_KWARGS)
def send_staff_new_order_notification(self, order_id: int) -> bool:
    return send_staff_new_order_notification_sync(order_id, raise_on_error=True, task=self)


@shared_task
def auto_cancel_expired_pickup_orders() -> dict[str, int]:
    from orders.services import OrderAutoCancellationService

    return OrderAutoCancellationService().cancel_expired_pickup_orders()
