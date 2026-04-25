import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from orders.models import Order

logger = logging.getLogger(__name__)


def _build_order_detail_url(order: Order) -> str:
    return f"{settings.SITE_URL}{reverse('users:order_detail', kwargs={'pk': order.pk})}"


def _build_dashboard_order_detail_url(order: Order) -> str:
    return f"{settings.SITE_URL}{reverse('store:dashboard_order_detail', kwargs={'pk': order.pk})}"


def _build_order_notification_content(order: Order, event_key: str) -> tuple[str, str]:
    order_number = order.number or str(order.pk)
    detail_url = _build_order_detail_url(order)
    base_lines = [
        f"Заказ: {order_number}",
        f"Сумма: {order.total_amount} {order.currency}",
        f"Детали заказа: {detail_url}",
    ]

    if event_key == "created":
        subject = f"Заказ {order_number} принят"
        lines = [
            "Спасибо за заказ в Matchday Store.",
            "Мы приняли ваш заказ и начали его обработку.",
            f"Самовывоз: {settings.STORE_PICKUP_LOCATION_NAME}",
            f"Адрес: {settings.STORE_PICKUP_ADDRESS}",
            f"Часы работы: {settings.STORE_PICKUP_HOURS}",
            "Оплата производится при получении.",
        ]
    elif event_key == "cancelled":
        subject = f"Заказ {order_number} отменен"
        lines = [
            "Ваш заказ отменен.",
            "Если отмена произошла по ошибке, оформите новый заказ или свяжитесь с магазином.",
            f"Телефон магазина: {settings.STORE_PICKUP_PHONE}",
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
        logger.warning("Некоторые адреса в STAFF_ORDER_NOTIFICATION_EMAILS имеют неверный формат и будут пропущены")

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
        "Новый заказ в Matchday Store.",
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


def send_order_notification_sync(order_id: int, event_key: str) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error("Ошибка отправки уведомления по заказу: не настроен DEFAULT_FROM_EMAIL")
        return False

    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("Заказ %s не найден, уведомление %s не отправлено", order_id, event_key)
        return False

    if not order.email:
        logger.warning("У заказа %s отсутствует email, уведомление %s не отправлено", order_id, event_key)
        return False

    subject, message = _build_order_notification_content(order, event_key)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
        logger.info("Уведомление %s отправлено для заказа %s", event_key, order_id)
        return True
    except Exception:
        logger.exception("Ошибка отправки уведомления %s для заказа %s", event_key, order_id)
        return False


def send_staff_new_order_notification_sync(order_id: int) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error("Ошибка отправки staff-уведомления: не настроен DEFAULT_FROM_EMAIL")
        return False

    recipient_list = _get_staff_order_notification_recipients()
    if not recipient_list:
        logger.warning("STAFF_ORDER_NOTIFICATION_EMAILS пуст, staff-уведомление о заказе %s пропущено", order_id)
        return False

    try:
        order = Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("Заказ %s не найден, staff-уведомление не отправлено", order_id)
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
        logger.info("Staff-уведомление о новом заказе %s отправлено", order_id)
        return True
    except Exception:
        logger.exception("Ошибка отправки staff-уведомления о новом заказе %s", order_id)
        return False


@shared_task
def send_order_notification(order_id: int, event_key: str) -> bool:
    return send_order_notification_sync(order_id, event_key)


@shared_task
def send_staff_new_order_notification(order_id: int) -> bool:
    return send_staff_new_order_notification_sync(order_id)
