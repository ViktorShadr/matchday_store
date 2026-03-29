from django.contrib.auth import user_logged_in
from django.dispatch import receiver

from store.services.cart_service import CartService


@receiver(user_logged_in)
def merge_carts_on_login(sender, request, user, **kwargs):
    """
    Объединяет корзины при входе пользователя в систему.
    """
    if request.session.session_key:
        CartService.merge_carts_on_login(user, request.session.session_key)
