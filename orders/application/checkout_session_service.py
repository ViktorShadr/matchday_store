from uuid import uuid4

from orders.models import Order
from store.site_contacts import build_pickup_location


class CheckoutSessionService:
    """Управление session-state сценария checkout."""

    checkout_token_session_key = "_checkout_token"
    checkout_processed_session_key = "_checkout_processed"

    def get_processed_order_for_token(self, request, submitted_token: str):
        if not submitted_token:
            return None

        processed_checkout = request.session.get(self.checkout_processed_session_key) or {}
        if processed_checkout.get("token") != submitted_token:
            return None

        order_id = processed_checkout.get("order_id")
        if not order_id:
            return None

        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return None

        if self.can_access_order(request, order):
            return order
        return None

    def get_or_create_checkout_token(self, request) -> str:
        token = request.session.get(self.checkout_token_session_key)
        if not token:
            token = uuid4().hex
            request.session[self.checkout_token_session_key] = token
            request.session.modified = True
        return token

    @staticmethod
    def build_pickup_location() -> dict[str, str]:
        return build_pickup_location()

    def has_processed_order(self, request, order_id: int) -> bool:
        processed_checkout = request.session.get(self.checkout_processed_session_key) or {}
        return str(processed_checkout.get("order_id") or "") == str(order_id)

    def can_access_order(self, request, order: Order) -> bool:
        if request.user.is_authenticated and order.user_id == request.user.id:
            return True
        if order.user_id is None and self.has_processed_order(request, order.pk):
            return True
        return False

    def mark_checkout_processed(self, request, submitted_token: str, order_id: int) -> None:
        request.session[self.checkout_processed_session_key] = {
            "token": submitted_token,
            "order_id": order_id,
        }
        request.session.pop(self.checkout_token_session_key, None)
        request.session.modified = True
