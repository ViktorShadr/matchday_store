from dataclasses import dataclass
from typing import Optional

from store.application import CartContext


@dataclass(slots=True)
class CheckoutContext:
    """Явный контекст checkout без привязки к Django request."""

    user: Optional[object]
    cart_context: CartContext
    ip_address: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None and getattr(self.user, "is_authenticated", True)

    @property
    def user_id(self) -> Optional[int]:
        if not self.is_authenticated:
            return None
        return getattr(self.user, "id", None)

    @property
    def user_for_order(self):
        return self.user if self.is_authenticated else None

    @property
    def session_key(self) -> Optional[str]:
        return self.cart_context.session_key
