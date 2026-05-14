import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from support.models import SupportRequest

logger = logging.getLogger(__name__)


def _get_support_notification_recipients() -> list[str]:
    raw_recipients = getattr(settings, "SUPPORT_NOTIFICATION_EMAILS", [])
    if isinstance(raw_recipients, str):
        raw_recipients = raw_recipients.split(",")

    recipients = [email.strip() for email in raw_recipients if isinstance(email, str) and email.strip()]
    valid_recipients = [email for email in recipients if "@" in email]

    if valid_recipients:
        return valid_recipients

    fallback_email = getattr(settings, "STORE_SUPPORT_EMAIL", "")
    if fallback_email and "@" in fallback_email:
        return [fallback_email]
    return []


def _build_support_request_admin_url(support_request: SupportRequest) -> str:
    path = reverse("admin:support_supportrequest_change", args=[support_request.pk])
    return f"{settings.SITE_URL}{path}"


def _build_support_notification_content(support_request: SupportRequest) -> tuple[str, str]:
    subject = f"Новое обращение в поддержку: {support_request.subject}"
    lines = [
        f"Новое обращение в поддержку магазина {settings.STORE_BRAND_NAME}.",
        "",
        f"Тема: {support_request.subject}",
        f"Статус: {support_request.get_status_display()}",
        f"Имя: {support_request.name}",
        f"Email: {support_request.email}",
        f"Телефон: {support_request.phone or '—'}",
        "",
        "Сообщение:",
        support_request.message,
        "",
        f"Открыть в admin: {_build_support_request_admin_url(support_request)}",
    ]
    return subject, "\n".join(lines)


@shared_task
def send_support_request_notification(support_request_id: int) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        SupportRequest.objects.filter(pk=support_request_id).update(
            email_sent=False,
            email_error="DEFAULT_FROM_EMAIL не настроен.",
        )
        logger.error("Не настроен DEFAULT_FROM_EMAIL для уведомления поддержки")
        return False

    recipients = _get_support_notification_recipients()
    if not recipients:
        SupportRequest.objects.filter(pk=support_request_id).update(
            email_sent=False,
            email_error="Не настроены получатели уведомлений поддержки.",
        )
        logger.error("Не настроены получатели уведомлений поддержки")
        return False

    try:
        support_request = SupportRequest.objects.get(pk=support_request_id)
    except SupportRequest.DoesNotExist:
        logger.warning("Обращение в поддержку %s не найдено, уведомление не отправлено", support_request_id)
        return False

    subject, message = _build_support_notification_content(support_request)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:
        support_request.email_sent = False
        support_request.email_error = str(exc)
        support_request.save(update_fields=["email_sent", "email_error", "updated_at"])
        logger.exception(
            "Ошибка отправки уведомления поддержки",
            extra={"support_request_id": support_request_id},
        )
        return False

    support_request.email_sent = True
    support_request.email_error = None
    support_request.save(update_fields=["email_sent", "email_error", "updated_at"])
    logger.info("Уведомление поддержки отправлено", extra={"support_request_id": support_request_id})
    return True
