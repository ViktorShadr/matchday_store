from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView
from django_ratelimit.decorators import ratelimit

from config.rate_limits import setting_rate
from support.application import SupportNotificationService
from support.forms import SupportRequestForm


def _build_ratelimit_response(view, request):
    messages.error(request, "Слишком много обращений. Попробуйте отправить форму позже.")
    response = view.get(request, *view.args, **view.kwargs)
    response.status_code = 429
    return response


@method_decorator(
    ratelimit(
        key="ip",
        rate=setting_rate("RATELIMIT_SUPPORT_POST_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
class SupportRequestView(FormView):
    template_name = "support/request_form.html"
    form_class = SupportRequestForm
    success_url = reverse_lazy("support:success")

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and getattr(request, "limited", False):
            return _build_ratelimit_response(self, request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        support_request = form.save(commit=False)
        if self.request.user.is_authenticated:
            support_request.user = self.request.user
        support_request.save()

        SupportNotificationService.schedule(support_request.pk)
        messages.success(self.request, "Обращение принято. Мы ответим на указанный email.")
        return HttpResponseRedirect(self.get_success_url())


class SupportSuccessView(TemplateView):
    template_name = "support/success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["support_email"] = settings.STORE_SUPPORT_EMAIL
        context["catalog_url"] = reverse("store:product_list")
        return context
