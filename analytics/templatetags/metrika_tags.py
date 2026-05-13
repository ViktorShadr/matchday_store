from django import template

register = template.Library()


@register.inclusion_tag("analytics/_yandex_metrika.html", takes_context=True)
def yandex_metrika(context):
    """Render the Metrica tag and page-specific ecommerce events once from base.html."""
    config = context.get("yandex_metrika") or {}
    events = []

    for event_source_name in ("metrika_pending_events", "metrika_page_events"):
        event_source = context.get(event_source_name) or []
        if isinstance(event_source, list):
            events.extend(event for event in event_source if isinstance(event, dict))

    return {
        "yandex_metrika": config,
        "metrika_ecommerce_events": events,
    }
