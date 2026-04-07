from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Конфигурация приложения PaymentsConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self):
        """Инициализация приложения при запуске."""
        import payments.signals
