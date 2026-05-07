import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.models import User
from users.tasks import send_confirmation_email, send_confirmation_email_sync

logger = logging.getLogger(__name__)


class EmailConfirmationService:
    """Прикладной сервис подтверждения email пользователя."""

    resend_cooldown_seconds = 60

    @staticmethod
    def send_confirmation_email_with_fallback(
        user_email: str,
        confirmation_token: str,
        async_sender=None,
        sync_sender=None,
    ) -> bool:
        async_sender = async_sender or send_confirmation_email
        sync_sender = sync_sender or send_confirmation_email_sync
        try:
            async_sender.delay(user_email, confirmation_token)
            return True
        except Exception:
            logger.exception(
                "Ошибка постановки задачи отправки подтверждения для %s, используем sync fallback",
                user_email,
                extra={"event": "confirmation_email_dispatch_failed"},
            )
            return sync_sender(user_email, confirmation_token)

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
            # Rollout-safe fallback for legacy tokens issued before
            # `email_token_created_at` was introduced.
            return False
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
            is_sent = cls.send_confirmation_email_with_fallback(user.email, confirmation_token)
            send_result["success"] = is_sent
            if is_sent:
                User.objects.filter(pk=user.pk).update(confirmation_email_last_sent_at=timezone.now())

        transaction.on_commit(_dispatch_confirmation_email)
        return confirmation_token

    @classmethod
    def resend_confirmation(cls, user: User) -> bool:
        confirmation_token = cls.generate_token()
        if not cls.send_confirmation_email_with_fallback(user.email, confirmation_token):
            return False

        user.email_token = confirmation_token
        user.email_token_created_at = timezone.now()
        user.confirmation_email_last_sent_at = timezone.now()
        user.save(update_fields=["email_token", "email_token_created_at", "confirmation_email_last_sent_at"])
        return True
