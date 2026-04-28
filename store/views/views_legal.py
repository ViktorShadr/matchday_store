from django.views.generic import TemplateView
from django.urls import reverse_lazy

from store.mixins.cart_mixins import CartContextMixin


class LegalPageMixin(CartContextMixin):
    """Миксин для добавления breadcrumbs на юридические страницы"""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": self.page_title, "url": None},
        ]
        return context


class PrivacyPolicyView(LegalPageMixin, TemplateView):
    template_name = "main_page/legal/privacy_policy.html"
    page_title = "Политика конфиденциальности"


class TermsOfServiceView(LegalPageMixin, TemplateView):
    template_name = "main_page/legal/terms_of_service.html"
    page_title = "Пользовательское соглашение"


class ReturnPolicyView(LegalPageMixin, TemplateView):
    template_name = "main_page/legal/return_policy.html"
    page_title = "Условия возврата"


class OfferView(LegalPageMixin, TemplateView):
    template_name = "main_page/legal/offer.html"
    page_title = "Договор оферты"


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
