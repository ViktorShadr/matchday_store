import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.email_delivery import build_email_delivery_log_extra
from users.models import User
from users.tasks import send_confirmation_email

logger = logging.getLogger(__name__)


class EmailConfirmationService:
    """Прикладной сервис подтверждения email пользователя."""

    resend_cooldown_seconds = 60

    @staticmethod
    def enqueue_confirmation_email(
        user_email: str,
        confirmation_token: str,
        async_sender=None,
    ) -> bool:
        async_sender = async_sender or send_confirmation_email
        try:
            async_sender.delay(user_email, confirmation_token)
            return True
        except Exception as exc:
            logger.exception(
                "user.email_confirmation_enqueue_failed",
                extra=build_email_delivery_log_extra(
                    event="user.email_confirmation_enqueue_failed",
                    error_type=exc.__class__.__name__,
                    email_type="confirmation",
                ),
            )
            return False

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def token_ttl() -> timedelta:
        ttl_hours = max(getattr(settings, "EMAIL_CONFIRMATION_TOKEN_TTL_HOURS", 24), 1)
        return timedelta(hours=ttl_hours)

    @classmethod
    def is_token_expired(cls, user: User) -> bool:
        if not user.email_token_created_at:
            # Legacy tokens without a creation timestamp are treated as expired
            # to prevent permanent tokens from surviving indefinitely.
            return True
        return timezone.now() >= user.email_token_created_at + cls.token_ttl()

    @classmethod
    def can_resend(cls, user) -> tuple[bool, int]:
        last_sent = user.confirmation_email_last_sent_at
        if last_sent is None:
            return True, 0

        elapsed_seconds = int((timezone.now() - last_sent).total_seconds())
        if elapsed_seconds >= cls.resend_cooldown_seconds:
            return True, 0
        return False, cls.resend_cooldown_seconds - elapsed_seconds

    @classmethod
    def schedule_confirmation_for_new_user(cls, user: User, send_result: dict) -> str:
        confirmation_token = user.generate_email_token()

        def _dispatch_confirmation_email():
            is_queued = cls.enqueue_confirmation_email(user.email, confirmation_token)
            send_result["success"] = is_queued
            if is_queued:
                User.objects.filter(pk=user.pk).update(confirmation_email_last_sent_at=timezone.now())

        transaction.on_commit(_dispatch_confirmation_email)
        return confirmation_token

    @classmethod
    def resend_confirmation(cls, user: User) -> bool:
        confirmation_token = cls.generate_token()
        if not cls.enqueue_confirmation_email(user.email, confirmation_token):
            return False

        user.email_token = confirmation_token
        user.email_token_created_at = timezone.now()
        user.confirmation_email_last_sent_at = timezone.now()
        user.save(update_fields=["email_token", "email_token_created_at", "confirmation_email_last_sent_at"])
        return True
