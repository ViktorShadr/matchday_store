import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from config.email_delivery import (
    EMAIL_TASK_AUTORETRY_KWARGS,
    EMAIL_TASK_MAX_RETRIES,
    NotificationDeliveryError,
    build_email_delivery_log_extra,
    get_email_task_retry_count,
    is_permanent_email_delivery_error,
)
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


def _set_support_request_delivery_failure(support_request_id: int, message: str) -> None:
    SupportRequest.objects.filter(pk=support_request_id).update(
        email_sent=False,
        email_error=message,
        updated_at=timezone.now(),
    )


def _set_support_request_delivery_success(support_request_id: int) -> None:
    SupportRequest.objects.filter(pk=support_request_id).update(
        email_sent=True,
        email_error=None,
        updated_at=timezone.now(),
    )


def _is_final_retry(retries: int) -> bool:
    return retries >= EMAIL_TASK_MAX_RETRIES


def _get_current_retry_count(task) -> int:
    return get_email_task_retry_count(task)


def send_support_request_notification_sync(
    support_request_id: int,
    *,
    raise_on_error: bool = False,
    retries: int = EMAIL_TASK_MAX_RETRIES,
    task=None,
) -> bool:
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        _set_support_request_delivery_failure(support_request_id, "DEFAULT_FROM_EMAIL не настроен.")
        logger.error(
            "Не настроен DEFAULT_FROM_EMAIL для уведомления поддержки",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                support_request_id=support_request_id,
                email_type="support",
            ),
        )
        return False

    recipients = _get_support_notification_recipients()
    if not recipients:
        _set_support_request_delivery_failure(support_request_id, "Не настроены получатели уведомлений поддержки.")
        logger.error(
            "Не настроены получатели уведомлений поддержки",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                support_request_id=support_request_id,
                email_type="support",
            ),
        )
        return False

    try:
        support_request = SupportRequest.objects.get(pk=support_request_id)
    except SupportRequest.DoesNotExist:
        logger.warning(
            "Обращение в поддержку %s не найдено, уведомление не отправлено",
            support_request_id,
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                support_request_id=support_request_id,
                email_type="support",
            ),
        )
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
        error_type = exc.__class__.__name__
        is_permanent_error = is_permanent_email_delivery_error(exc)
        logger.exception(
            "Ошибка отправки уведомления поддержки",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                support_request_id=support_request_id,
                email_type="support",
                error_type=error_type,
                reason="smtp_permanent_failure" if is_permanent_error else "send_mail_failed",
            ),
        )
        if is_permanent_error:
            _set_support_request_delivery_failure(support_request_id, str(exc))
            return False

        if raise_on_error and not _is_final_retry(retries):
            raise NotificationDeliveryError("Не удалось отправить уведомление поддержки") from exc

        _set_support_request_delivery_failure(support_request_id, str(exc))
        logger.error(
            "Уведомление поддержки не доставлено после исчерпания retry",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                support_request_id=support_request_id,
                email_type="support",
                error_type=error_type,
            ),
        )
        return False

    _set_support_request_delivery_success(support_request_id)
    logger.info(
        "Уведомление поддержки отправлено",
        extra=build_email_delivery_log_extra(
            task=task,
            retries=retries,
            support_request_id=support_request_id,
            email_type="support",
        ),
    )
    return True


@shared_task(**EMAIL_TASK_AUTORETRY_KWARGS)
def send_support_request_notification(self, support_request_id: int) -> bool:
    return send_support_request_notification_sync(
        support_request_id,
        raise_on_error=True,
        retries=_get_current_retry_count(self),
        task=self,
    )
