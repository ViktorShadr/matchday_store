from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings

SESSION_ECOMMERCE_EVENTS_KEY = "_metrika_ecommerce_events"
DEFAULT_CURRENCY_CODE = "RUB"


def is_metrika_enabled() -> bool:
    return bool(getattr(settings, "METRIKA_ACTIVE", False))


def build_metrika_config() -> dict[str, Any]:
    if not is_metrika_enabled():
        return {"enabled": False}

    counter_id = str(getattr(settings, "METRIKA_COUNTER_ID", "")).strip()
    return {
        "enabled": True,
        "counter_id": counter_id,
        "counterId": counter_id,
        "requireConsent": bool(getattr(settings, "METRIKA_REQUIRE_CONSENT", False)),
        "options": {
            "clickmap": True,
            "trackLinks": True,
            "accurateTrackBounce": True,
            "webvisor": True,
            "ecommerce": "dataLayer",
            "triggerEvent": True,
        },
    }


def build_metrika_context(request) -> dict[str, Any]:
    config = build_metrika_config()
    pending_events = []

    if config.get("enabled"):
        session = getattr(request, "session", None)
        if session is not None:
            pending_events = session.pop(SESSION_ECOMMERCE_EVENTS_KEY, [])

    return {
        "yandex_metrika": config,
        "metrika_pending_events": pending_events if isinstance(pending_events, list) else [],
    }


def queue_ecommerce_event(request, event: dict[str, Any] | None) -> None:
    if not is_metrika_enabled() or not event:
        return

    session = getattr(request, "session", None)
    if session is None:
        return

    events = session.get(SESSION_ECOMMERCE_EVENTS_KEY, [])
    if not isinstance(events, list):
        events = []
    events.append(event)
    session[SESSION_ECOMMERCE_EVENTS_KEY] = events
    session.modified = True


def decimal_to_number(value) -> float | None:
    if value in ("", None):
        return None

    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None

    return float(decimal_value.quantize(Decimal("0.01")))


def clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_variant_label(*parts) -> str:
    return " / ".join(part for part in (clean_text(part) for part in parts) if part)


def build_category_name(product=None, category=None) -> str:
    if category is not None:
        return clean_text(getattr(category, "name", category))

    product_category = getattr(product, "category", None)
    return clean_text(getattr(product_category, "name", product_category))


def build_sku(variant=None, fallback: str = "") -> str:
    sku = clean_text(getattr(variant, "sku", ""))
    if sku:
        return sku

    variant_id = getattr(variant, "id", None)
    if variant_id:
        return f"variant-{variant_id}"

    return clean_text(fallback)


def remove_empty_values(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            cleaned_item = remove_empty_values(item)
            if cleaned_item not in ("", None, [], {}):
                cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        return [remove_empty_values(item) for item in value if item not in ("", None, [], {})]
    return value


def build_variant_product_item(
    variant,
    *,
    quantity: int | None = None,
    list_name: str = "",
    position: int | None = None,
) -> dict[str, Any]:
    product = variant.product
    item = {
        "id": build_sku(variant, fallback=f"product-{product.pk}"),
        "sku": build_sku(variant, fallback=f"product-{product.pk}"),
        "name": clean_text(product.name),
        "brand": clean_text(getattr(settings, "STORE_BRAND_NAME", "")),
        "category": build_category_name(product=product),
        "variant": build_variant_label(getattr(variant, "size", ""), getattr(variant, "color", "")),
        "price": decimal_to_number(getattr(variant, "price", None)),
        "quantity": quantity,
        "list": clean_text(list_name),
        "position": position,
    }
    return remove_empty_values(item)


def build_product_detail_event(product) -> dict[str, Any] | None:
    variants = list(product.variants.all())
    variant = next((item for item in variants if item.available_quantity > 0), None) or (
        variants[0] if variants else None
    )
    if variant is None:
        price = decimal_to_number(getattr(product, "display_price", None))
        item = {
            "id": f"product-{product.pk}",
            "sku": f"product-{product.pk}",
            "name": clean_text(product.name),
            "brand": clean_text(getattr(settings, "STORE_BRAND_NAME", "")),
            "category": build_category_name(product=product),
            "price": price,
        }
    else:
        item = build_variant_product_item(variant, list_name="Product detail")

    return build_ecommerce_event("view_item", "detail", [item])


def build_add_to_cart_event(cart_item, quantity: int) -> dict[str, Any] | None:
    item = build_variant_product_item(
        cart_item.product_variant,
        quantity=quantity,
        list_name="Add to cart",
    )
    return build_ecommerce_event("add_to_cart", "add", [item])


def build_checkout_event(cart_items, total_price=None) -> dict[str, Any] | None:
    products = [
        build_variant_product_item(
            item.product_variant,
            quantity=item.quantity,
            list_name="Checkout",
            position=position,
        )
        for position, item in enumerate(cart_items, start=1)
    ]
    if not products:
        return None

    action_field = {
        "step": 1,
        "option": "pickup",
        "revenue": decimal_to_number(total_price),
    }
    return build_ecommerce_event("begin_checkout", "checkout", products, action_field=action_field)


def build_order_product_item(order_item, position: int) -> dict[str, Any]:
    variant = order_item.product_variant
    product = getattr(variant, "product", None)
    sku = clean_text(order_item.sku_snapshot) or build_sku(variant, fallback=f"order-item-{order_item.pk}")
    item = {
        "id": sku,
        "sku": sku,
        "name": clean_text(order_item.product_name_snapshot),
        "brand": clean_text(getattr(settings, "STORE_BRAND_NAME", "")),
        "category": build_category_name(product=product),
        "variant": build_variant_label(order_item.size_snapshot, order_item.color_snapshot),
        "price": decimal_to_number(order_item.unit_price),
        "quantity": order_item.quantity,
        "line_total": decimal_to_number(order_item.line_total),
        "position": position,
    }
    return remove_empty_values(item)


def build_purchase_event(order, order_items) -> dict[str, Any] | None:
    products = [
        build_order_product_item(order_item, position) for position, order_item in enumerate(order_items, start=1)
    ]
    if not products:
        return None

    action_field = {
        "id": clean_text(order.number) or str(order.pk),
        "revenue": decimal_to_number(order.total_amount),
    }
    return build_ecommerce_event(
        "purchase",
        "purchase",
        products,
        action_field=action_field,
        currency=clean_text(order.currency) or DEFAULT_CURRENCY_CODE,
    )


def build_ecommerce_event(
    event_name: str,
    action_name: str,
    products: list[dict[str, Any]],
    *,
    action_field: dict[str, Any] | None = None,
    currency: str = DEFAULT_CURRENCY_CODE,
) -> dict[str, Any] | None:
    if not products:
        return None

    action_payload = {"products": products}
    if action_field:
        action_payload["actionField"] = remove_empty_values(action_field)

    return remove_empty_values(
        {
            "event": event_name,
            "ecommerce": {
                "currencyCode": currency,
                action_name: action_payload,
            },
        }
    )
