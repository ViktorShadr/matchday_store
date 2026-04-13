from django.apps import AppConfig


class StoreConfig(AppConfig):
    """Конфигурация приложения StoreConfig."""

    name = "store"

    def ready(self):
        """Выполняет инициализацию приложения при запуске."""
        import store.signals
