from analytics.metrika import build_metrika_context


def yandex_metrika(request):
    """Expose Yandex Metrica config and queued events to base templates."""
    return build_metrika_context(request)
