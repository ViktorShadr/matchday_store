from dataclasses import dataclass

from store.application import CartContext


@dataclass(slots=True)
class CheckoutContext:
    """Явный контекст checkout без привязки к Django request."""

    user: object
    cart_context: CartContext

    @property
    def user_id(self) -> int:
        return self.user.id
