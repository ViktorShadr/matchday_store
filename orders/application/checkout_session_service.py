from uuid import uuid4

from django.conf import settings

from orders.models import Order


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
            return Order.objects.get(pk=order_id, user=request.user)
        except Order.DoesNotExist:
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
        return {
            "code": settings.STORE_PICKUP_LOCATION_CODE,
            "name": settings.STORE_PICKUP_LOCATION_NAME,
            "address": settings.STORE_PICKUP_ADDRESS,
            "hours": settings.STORE_PICKUP_HOURS,
            "phone": settings.STORE_PICKUP_PHONE,
        }

    def mark_checkout_processed(self, request, submitted_token: str, order_id: int) -> None:
        request.session[self.checkout_processed_session_key] = {
            "token": submitted_token,
            "order_id": order_id,
        }
        request.session.pop(self.checkout_token_session_key, None)
        request.session.modified = True
