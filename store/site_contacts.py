from django.conf import settings


def format_business_days_label(days: int) -> str:
    normalized_days = int(days)
    if normalized_days % 10 == 1 and normalized_days % 100 != 11:
        word = "рабочий день"
    elif normalized_days % 10 in (2, 3, 4) and normalized_days % 100 not in (12, 13, 14):
        word = "рабочих дня"
    else:
        word = "рабочих дней"
    return f"{normalized_days} {word}"


def build_pickup_location() -> dict[str, str]:
    return {
        "code": settings.STORE_PICKUP_LOCATION_CODE,
        "name": settings.STORE_PICKUP_LOCATION_NAME,
        "address": settings.STORE_PICKUP_ADDRESS,
        "hours": settings.STORE_PICKUP_HOURS,
        "phone": settings.STORE_PICKUP_PHONE,
    }


def build_store_contacts() -> dict:
    return {
        "brand_name": settings.STORE_BRAND_NAME,
        "support_email": settings.STORE_SUPPORT_EMAIL,
        "pickup_location": build_pickup_location(),
        "pickup_retention_business_days": settings.ORDER_PICKUP_RETENTION_BUSINESS_DAYS,
        "pickup_retention_label": format_business_days_label(settings.ORDER_PICKUP_RETENTION_BUSINESS_DAYS),
    }
