from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ICheckoutService(ABC):
    """Интерфейс для сервиса оформления заказа (ISP)."""

    @abstractmethod
    def create_order_from_cart(
        self, request, cleaned_data: Dict[str, Any], checkout_token: Optional[str] = None
    ):
        """Создать заказ из корзины."""
        pass
