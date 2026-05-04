import logging
from dataclasses import dataclass
from typing import Optional

from django.db import IntegrityError, transaction

from store.models import Cart, CartItem
from store.repositories import CartRepository, ICartRepository
from store.services.cart_exceptions import CartOperationError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CartContext:
    """Явный контекст корзины, отделенный от HTTP request."""

    cart: Cart
    user_id: Optional[int]
    session_key: Optional[str]
    is_authenticated: bool

    @property
    def actor_label(self):
        return self.user_id if self.is_authenticated and self.user_id is not None else "anonymous"


class CartContextResolver:
    """Разрешает cart context из request/user/session и управляет merge корзин."""

    request_cache_attr = "_resolved_cart_context"

    def __init__(self, cart_repository: Optional[ICartRepository] = None):
        self.cart_repository = cart_repository or CartRepository()

    def resolve_request(self, request) -> CartContext:
        cached_context = getattr(request, self.request_cache_attr, None)
        if cached_context is not None:
            return cached_context

        if request.user.is_authenticated:
            cart = self.cart_repository.get_or_create_cart_by_user(request.user)
            session_key = request.session.session_key
            if session_key:
                self.merge_session_cart_into_user_cart(user_cart=cart, session_key=session_key)
            cart_context = CartContext(
                cart=cart,
                user_id=request.user.id,
                session_key=session_key,
                is_authenticated=True,
            )
        else:
            session_key = self._ensure_session_key(request)
            cart = self.cart_repository.get_or_create_cart_by_session(session_key)
            cart_context = CartContext(
                cart=cart,
                user_id=None,
                session_key=session_key,
                is_authenticated=False,
            )

        setattr(request, self.request_cache_attr, cart_context)
        return cart_context

    def merge_on_login(self, user, session_key: str) -> None:
        if not session_key:
            return
        user_cart = self.cart_repository.get_or_create_cart_by_user(user)
        self.merge_session_cart_into_user_cart(user_cart=user_cart, session_key=session_key)

    def _ensure_session_key(self, request) -> str:
        if not request.session.session_key:
            request.session.create()
            request.session.modified = True
        return request.session.session_key

    @transaction.atomic
    def merge_session_cart_into_user_cart(self, user_cart: Cart, session_key: str) -> None:
        try:
            session_cart = self.cart_repository.get_cart_by_session_key(session_key)
            if not session_cart:
                return

            locked_carts = {
                cart.pk: cart
                for cart in Cart.objects.select_for_update()
                .filter(pk__in=[user_cart.pk, session_cart.pk])
                .order_by("pk")
            }
            locked_user_cart = locked_carts.get(user_cart.pk)
            locked_session_cart = locked_carts.get(session_cart.pk)
            if locked_user_cart is None or locked_session_cart is None:
                return

            items = list(
                locked_session_cart.items.select_related("product_variant").select_for_update().order_by("pk")
            )

            for item in items:
                available_quantity = item.product_variant.available_quantity
                if available_quantity < 1:
                    continue

                cart_item = (
                    locked_user_cart.items.select_for_update().filter(product_variant=item.product_variant).first()
                )
                created = False
                if cart_item is None:
                    try:
                        with transaction.atomic():
                            cart_item = CartItem.objects.create(
                                cart=locked_user_cart,
                                product_variant=item.product_variant,
                                quantity=item.quantity,
                            )
                            created = True
                    except IntegrityError:
                        cart_item = locked_user_cart.items.select_for_update().get(
                            product_variant=item.product_variant
                        )

                if created and cart_item.quantity > available_quantity:
                    cart_item.quantity = available_quantity
                    cart_item.save()
                elif not created:
                    new_quantity = min(cart_item.quantity + item.quantity, available_quantity)
                    if cart_item.quantity != new_quantity:
                        cart_item.quantity = new_quantity
                        cart_item.save()
                    logger.info(
                        "Merged cart item: user=%s, variant=%s, qty=%s",
                        user_cart.user.id if user_cart.user_id else "anonymous",
                        item.product_variant.id,
                        cart_item.quantity,
                    )

            self.cart_repository.delete_cart(locked_session_cart)
            logger.info("Session cart %s... merged and deleted", session_key[:8])
        except Exception as exc:
            logger.error("Error merging carts: %s", exc, exc_info=True)
            raise CartOperationError(f"Ошибка при объединении корзин: {str(exc)}")
