from django.db.utils import OperationalError, ProgrammingError
from django.urls import reverse

from store.models import Page
from store.services import PermissionService

LEGAL_PAGE_URLS = (
    ("privacy-policy", "privacy_policy"),
    ("terms-of-service", "terms_of_service"),
    ("return-policy", "return_policy"),
    ("offer", "offer"),
)


def navigation_permissions(request):
    """Добавляет права пользователя в общий контекст шаблонов."""
    legal_page_urls = {url_name: None for _, url_name in LEGAL_PAGE_URLS}
    try:
        published_pages = {
            page.slug
            for page in Page.objects.filter(
                is_published=True,
                slug__in=[slug for slug, _ in LEGAL_PAGE_URLS],
            ).only("slug")
        }
        for slug, url_name in LEGAL_PAGE_URLS:
            legal_page_urls[url_name] = reverse(f"store:{url_name}") if slug in published_pages else None
    except (OperationalError, ProgrammingError):
        # Таблица store_page может отсутствовать до применения миграций.
        pass

    return {
        "navigation_permissions": PermissionService.get_user_permissions(request.user),
        "legal_page_urls": legal_page_urls,
    }
