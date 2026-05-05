from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Конфигурация приложения PaymentsConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self):
        # Регистрируем signal handlers для синхронизации Order.payment_status
        import payments.signals  # noqa: F401
