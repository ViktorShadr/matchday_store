from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, RedirectView, TemplateView, UpdateView

from orders.application import DashboardOrderFlowError, DashboardOrderFlowService
from orders.models import Order
from store.application import WarehouseCrudService
from store.forms import CategoryForm, ProductForm, ProductImageForm, ProductVariantForm, VariantStockForm
from store.mixins import ModeratorRequiredMixin
from store.models import Category, Product, ProductImage, ProductVariant
from store.presenters import DashboardOrderPresenter, WarehouseProductPresenter, WarehouseUiPresenter
from store.queries import DashboardOrderQueryService, WarehouseManagementQueryService, WarehouseQueryService


DASHBOARD_ORDER_STATUS_CHOICES = DashboardOrderPresenter.STATUS_CHOICES
DASHBOARD_ORDER_FILTERS = DashboardOrderPresenter.STATUS_FILTERS
DASHBOARD_ORDER_STATUS_KEYS = DashboardOrderQueryService.STATUS_KEYS
FINAL_DASHBOARD_ORDER_STATUS_KEYS = DashboardOrderPresenter.FINAL_STATUS_KEYS
DASHBOARD_PAYMENT_STATUS_CHOICES = DashboardOrderPresenter.PAYMENT_STATUS_CHOICES
DASHBOARD_PAYMENT_STATUS_KEYS = {choice[0] for choice in DASHBOARD_PAYMENT_STATUS_CHOICES}


class DashboardHomeView(ModeratorRequiredMixin, RedirectView):
    pattern_name = "store:warehouse_dashboard"
    permanent = False


class WarehouseDashboardView(ModeratorRequiredMixin, TemplateView):
    template_name = "dashboard/warehouse.html"

    SORT_OPTION_LABELS = (
        ("updated_desc", "Сначала новые"),
        ("name_asc", "Название: А-Я"),
        ("name_desc", "Название: Я-А"),
        ("stock_desc", "Остаток: больше"),
        ("stock_asc", "Остаток: меньше"),
        ("price_asc", "Цена: дешевле"),
        ("price_desc", "Цена: дороже"),
    )

    STOCK_FILTER_LABELS = (
        ("", "Все остатки"),
        ("in_stock", "В наличии"),
        ("low_stock", "Мало осталось"),
        ("out_of_stock", "Нет в наличии"),
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        selected_category = self.request.GET.get("category", "").strip()
        selected_stock_filter = self.request.GET.get("stock", "").strip()
        selected_sort = WarehouseQueryService.normalize_sort(self.request.GET.get("sort", "updated_desc").strip() or "updated_desc")
        products_queryset = WarehouseQueryService.build_products_queryset(
            search_query=search_query,
            selected_category=selected_category,
            selected_stock_filter=selected_stock_filter,
            selected_sort=selected_sort,
        )

        context["products"] = WarehouseProductPresenter.present_many(list(products_queryset))
        context["categories"] = WarehouseQueryService.build_categories_queryset()
        context["search_query"] = search_query
        context["selected_category"] = selected_category
        context["selected_stock_filter"] = selected_stock_filter
        context["selected_sort"] = selected_sort
        context["sort_options"] = self.SORT_OPTION_LABELS
        context["stock_filter_options"] = self.STOCK_FILTER_LABELS
        context["has_active_filters"] = bool(search_query or selected_category or selected_stock_filter)
        return context


class OrdersDashboardView(ModeratorRequiredMixin, TemplateView):
    template_name = "dashboard/orders.html"

    @staticmethod
    def _build_status_filter_links(search_query: str):
        filters = []
        for key, label in DASHBOARD_ORDER_FILTERS:
            params = {}
            if key != "all":
                params["status"] = key
            if search_query:
                params["q"] = search_query
            query_string = urlencode(params)
            filters.append(
                {
                    "key": key,
                    "label": label,
                    "url": f"?{query_string}" if query_string else "?",
                }
            )
        return filters

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = DashboardOrderQueryService.normalize_status_filter(
            self.request.GET.get("status", "all").strip() or "all"
        )
        search_query = self.request.GET.get("q", "").strip()
        orders_queryset = DashboardOrderQueryService.build_orders_queryset(
            status_filter=status_filter,
            search_query=search_query,
        )
        context["orders"] = DashboardOrderPresenter.present_many(list(orders_queryset))
        context["current_status_filter"] = status_filter
        context["search_query"] = search_query
        context["status_filters"] = self._build_status_filter_links(search_query)
        return context


class DashboardOrderDetailView(ModeratorRequiredMixin, DetailView):
    model = Order
    template_name = "dashboard/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("user").prefetch_related("items", "status_transitions__changed_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard_status_key = DashboardOrderPresenter.get_status_key(self.object)
        dashboard_status_meta = DashboardOrderPresenter.STATUS_META[dashboard_status_key]
        payment_status_meta = DashboardOrderPresenter.get_payment_meta(self.object)

        context["items"] = self.object.items.order_by("pk")
        context["status_choices"] = DashboardOrderPresenter.get_available_status_choices(self.object)
        context["payment_status_choices"] = DASHBOARD_PAYMENT_STATUS_CHOICES
        context["current_status_key"] = dashboard_status_key
        context["current_status_label"] = dashboard_status_meta["label"]
        context["current_status_badge"] = dashboard_status_meta["badge_class"]
        context["current_payment_status_key"] = self.object.payment_status
        context["current_payment_status_label"] = payment_status_meta["label"]
        context["current_payment_status_badge"] = payment_status_meta["badge_class"]
        context["staff_guidance"] = DashboardOrderPresenter.build_staff_guidance(self.object)
        context["status_transitions"] = self.object.status_transitions.select_related("changed_by").order_by(
            "-created_at",
            "-id",
        )
        return context


class DashboardOrderStatusUpdateView(ModeratorRequiredMixin, View):
    dashboard_order_flow_service = DashboardOrderFlowService()

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, pk=self.kwargs["pk"])
        next_status = request.POST.get("status", "").strip()
        if next_status not in DASHBOARD_ORDER_STATUS_KEYS:
            return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))

        try:
            result = self.dashboard_order_flow_service.update_order_status(order, next_status, actor=request.user)
        except DashboardOrderFlowError as exc:
            messages.error(request, str(exc))
        else:
            if result.message:
                messages.success(request, result.message)
        return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))


class DashboardOrderPaymentStatusUpdateView(ModeratorRequiredMixin, View):
    dashboard_order_flow_service = DashboardOrderFlowService()

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, pk=self.kwargs["pk"])
        next_payment_status = request.POST.get("payment_status", "").strip()
        if next_payment_status not in DASHBOARD_PAYMENT_STATUS_KEYS:
            return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))

        try:
            result = self.dashboard_order_flow_service.update_payment_status(
                order,
                next_payment_status,
                actor=request.user,
            )
        except DashboardOrderFlowError as exc:
            messages.error(request, str(exc))
        else:
            if result.message:
                messages.success(request, result.message)

        return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))


class WarehouseProductCreateView(ModeratorRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "dashboard/product_form.html"
    crud_service = WarehouseCrudService()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.product_create_context())
        return context

    def form_valid(self, form):
        self.object = self.crud_service.save_product(form, is_on_sale=False)
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.pk})


class WarehouseProductDeleteView(ModeratorRequiredMixin, DeleteView):
    model = Product
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"
    success_url = reverse_lazy("store:warehouse_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.product_delete_context(self.object))
        return context


class WarehouseCategoryCreateView(ModeratorRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "dashboard/category_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.category_create_context())
        return context

    def get_success_url(self):
        return reverse("store:warehouse_dashboard")


class WarehouseCategoryUpdateView(ModeratorRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "dashboard/category_form.html"
    context_object_name = "category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.category_update_context())
        return context

    def get_success_url(self):
        return reverse("store:warehouse_dashboard")


class WarehouseCategoryDeleteView(ModeratorRequiredMixin, DeleteView):
    model = Category
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"
    success_url = reverse_lazy("store:warehouse_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.category_delete_context())
        return context


class WarehouseProductManageView(ModeratorRequiredMixin, DetailView):
    model = Product
    template_name = "dashboard/product_manage.html"
    context_object_name = "product"
    crud_service = WarehouseCrudService()

    def get_queryset(self):
        return WarehouseManagementQueryService.get_product_manage_queryset()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        product_form = self.crud_service.update_product(self.object, request.POST)
        if product_form.is_valid():
            return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": self.object.pk}))

        context = self.get_context_data(product_form=product_form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            WarehouseManagementQueryService.build_product_manage_context(
                self.object,
                product_form=kwargs.get("product_form"),
            )
        )
        return context


class WarehouseProductPublishView(ModeratorRequiredMixin, View):
    crud_service = WarehouseCrudService()

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=self.kwargs["pk"])
        self.crud_service.set_product_sale_state(product, is_on_sale=True)
        messages.success(request, "Товар выставлен на продажу.")
        return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": product.pk}))


class WarehouseProductUnpublishView(ModeratorRequiredMixin, View):
    crud_service = WarehouseCrudService()

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=self.kwargs["pk"])
        self.crud_service.set_product_sale_state(product, is_on_sale=False)
        messages.success(request, "Товар снят с продажи.")
        return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": product.pk}))


class WarehouseVariantCreateView(ModeratorRequiredMixin, CreateView):
    model = ProductVariant
    form_class = ProductVariantForm
    template_name = "dashboard/variant_form.html"
    crud_service = WarehouseCrudService()

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product, pk=self.kwargs["product_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.product
        return kwargs

    def form_valid(self, form):
        self.object = self.crud_service.save_variant(form, product=self.product)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.variant_create_context(self.product))
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk})


class WarehouseVariantUpdateView(ModeratorRequiredMixin, UpdateView):
    model = ProductVariant
    form_class = ProductVariantForm
    template_name = "dashboard/variant_form.html"
    context_object_name = "variant"
    crud_service = WarehouseCrudService()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.object.product
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.variant_update_context(self.object))
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})

    def form_valid(self, form):
        self.object = self.crud_service.save_variant(form)
        return HttpResponseRedirect(self.get_success_url())


class WarehouseVariantDeleteView(ModeratorRequiredMixin, DeleteView):
    model = ProductVariant
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.variant_delete_context(self.object))
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})


class WarehouseVariantStockUpdateView(ModeratorRequiredMixin, View):
    crud_service = WarehouseCrudService()

    def post(self, request, *args, **kwargs):
        variant = get_object_or_404(ProductVariant, pk=self.kwargs["pk"])
        self.crud_service.update_variant_stock(variant, request.POST)
        return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": variant.product.pk}))


class WarehouseImageCreateView(ModeratorRequiredMixin, CreateView):
    model = ProductImage
    form_class = ProductImageForm
    template_name = "dashboard/image_form.html"
    crud_service = WarehouseCrudService()

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product, pk=self.kwargs["product_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = self.crud_service.save_product_image(form, self.product)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.image_create_context(self.product))
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk})


class WarehouseImageDeleteView(ModeratorRequiredMixin, DeleteView):
    model = ProductImage
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(WarehouseUiPresenter.image_delete_context(self.object))
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})
