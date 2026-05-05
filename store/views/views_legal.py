from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView

from store.mixins.cart_mixins import CartContextMixin
from store.models import Page


LEGAL_PAGE_ROUTES = (
    ("privacy-policy", "store:privacy_policy"),
    ("terms-of-service", "store:terms_of_service"),
    ("return-policy", "store:return_policy"),
    ("offer", "store:offer"),
)


class LegalPageView(CartContextMixin, TemplateView):
    """Единое представление контентных юридических страниц."""

    template_name = "main_page/legal/page_detail.html"
    page_slug = None

    def dispatch(self, request, *args, **kwargs):
        if not self.page_slug:
            raise ImproperlyConfigured("LegalPageView требует page_slug.")

        self.page = Page.objects.filter(is_published=True, slug=self.page_slug).first()
        if self.page is None:
            # Возвращаем штатную 404-страницу даже в DEBUG-режиме.
            return render(request, "main_page/404.html", status=404)
        return super().dispatch(request, *args, **kwargs)

    def get_legal_navigation(self):
        pages = {
            page.slug: page
            for page in Page.objects.filter(
                is_published=True,
                slug__in=[slug for slug, _ in LEGAL_PAGE_ROUTES],
            ).only("slug", "title")
        }
        navigation = []
        for slug, url_name in LEGAL_PAGE_ROUTES:
            page = pages.get(slug)
            if not page:
                continue
            navigation.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "url": reverse(url_name),
                }
            )
        return navigation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.page
        context["page"] = page
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": page.title, "url": None},
        ]
        context["legal_navigation"] = self.get_legal_navigation()
        return context


class PrivacyPolicyView(LegalPageView):
    page_slug = "privacy-policy"


class TermsOfServiceView(LegalPageView):
    page_slug = "terms-of-service"


class ReturnPolicyView(LegalPageView):
    page_slug = "return-policy"


class OfferView(LegalPageView):
    page_slug = "offer"


class Error404View(TemplateView):
    """Кастомная страница 404"""
    template_name = "main_page/404.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Страница не найдена", "url": None},
        ]
        return context


class Error500View(TemplateView):
    """Кастомная страница 500"""
    template_name = "main_page/500.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Ошибка сервера", "url": None},
        ]
        return context


# Function-based handlers for Django error handling
def error_404_view(request, exception=None):
    """Обработчик 404 ошибки"""
    from django.shortcuts import render
    return render(request, "main_page/404.html", status=404)


def error_500_view(request):
    """Обработчик 500 ошибки"""
    from django.shortcuts import render
    return render(request, "main_page/500.html", status=500)
