from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, RedirectView, TemplateView, UpdateView

from orders.models import Order
from store.forms import CategoryForm, ProductForm, ProductImageForm, ProductVariantForm, VariantStockForm
from store.mixins import ModeratorRequiredMixin
from store.models import Category, Product, ProductImage, ProductVariant


DASHBOARD_ORDER_STATUS_CHOICES = (
    ("new", "Новый"),
    ("processing", "В обработке"),
    ("ready", "Готов к выдаче"),
    ("issued", "Выдан"),
    ("cancelled", "Отменен"),
)

DASHBOARD_ORDER_FILTERS = (
    ("all", "Все"),
    ("new", "Новые"),
    ("processing", "В обработке"),
    ("ready", "Готов к выдаче"),
    ("issued", "Выдан"),
    ("cancelled", "Отменен"),
)

DASHBOARD_ORDER_STATUS_META = {
    "new": {
        "label": "Новый",
        "badge_class": "sf-status-badge sf-status-badge--warning",
    },
    "processing": {
        "label": "В обработке",
        "badge_class": "sf-status-badge sf-status-badge--info",
    },
    "ready": {
        "label": "Готов к выдаче",
        "badge_class": "sf-status-badge sf-status-badge--success",
    },
    "issued": {
        "label": "Выдан",
        "badge_class": "sf-status-badge sf-status-badge--dark",
    },
    "cancelled": {
        "label": "Отменен",
        "badge_class": "sf-status-badge sf-status-badge--danger",
    },
}

DASHBOARD_ORDER_STATUS_KEYS = {choice[0] for choice in DASHBOARD_ORDER_STATUS_CHOICES}


def _format_variant_label(variant_count: int) -> str:
    if variant_count % 10 == 1 and variant_count % 100 != 11:
        word = "вариант"
    elif variant_count % 10 in (2, 3, 4) and variant_count % 100 not in (12, 13, 14):
        word = "варианта"
    else:
        word = "вариантов"
    return f"{variant_count} {word}"


def _resolve_stock_state(stock_total: int) -> tuple[str, str]:
    if stock_total <= 0:
        return "out", "Нет в наличии"
    if stock_total < 5:
        return "low", f"Мало осталось: {stock_total}"
    return "in", f"В наличии: {stock_total}"


def _get_dashboard_order_status_key(order: Order) -> str:
    if order.status == Order.Status.CANCELLED or order.fulfillment_status == Order.FulfillmentStatus.CANCELLED:
        return "cancelled"
    if order.fulfillment_status == Order.FulfillmentStatus.DELIVERED:
        return "issued"
    if order.fulfillment_status == Order.FulfillmentStatus.RESERVED:
        return "ready"
    if order.fulfillment_status in {Order.FulfillmentStatus.PACKING, Order.FulfillmentStatus.SHIPPED}:
        return "processing"
    return "new"


def _apply_dashboard_order_status(order: Order, status_key: str) -> None:
    if status_key == "new":
        order.fulfillment_status = Order.FulfillmentStatus.NEW
        order.status = Order.Status.PLACED
        order.cancelled_at = None
        return
    if status_key == "processing":
        order.fulfillment_status = Order.FulfillmentStatus.PACKING
        order.status = Order.Status.PROCESSING
        order.cancelled_at = None
        return
    if status_key == "ready":
        order.fulfillment_status = Order.FulfillmentStatus.RESERVED
        order.status = Order.Status.PROCESSING
        order.cancelled_at = None
        return
    if status_key == "issued":
        order.fulfillment_status = Order.FulfillmentStatus.DELIVERED
        order.status = Order.Status.DELIVERED
        order.cancelled_at = None
        return
    if status_key == "cancelled":
        order.fulfillment_status = Order.FulfillmentStatus.CANCELLED
        order.status = Order.Status.CANCELLED
        if order.cancelled_at is None:
            order.cancelled_at = timezone.now()
        return
    raise ValueError(f"Unsupported dashboard status: {status_key}")


class DashboardHomeView(ModeratorRequiredMixin, RedirectView):
    pattern_name = "store:warehouse_dashboard"
    permanent = False


class WarehouseDashboardView(ModeratorRequiredMixin, TemplateView):
    template_name = "dashboard/warehouse.html"

    SORT_OPTIONS = {
        "updated_desc": ("-updated_at",),
        "name_asc": ("name",),
        "name_desc": ("-name",),
        "stock_desc": ("-stock_total", "name"),
        "stock_asc": ("stock_total", "name"),
        "price_asc": ("min_price", "name"),
        "price_desc": ("-min_price", "name"),
    }

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
        selected_sort = self.request.GET.get("sort", "updated_desc").strip() or "updated_desc"
        if selected_sort not in self.SORT_OPTIONS:
            selected_sort = "updated_desc"

        products_queryset = (
            Product.objects.select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "-created_at"),
                )
            )
            .annotate(
                variant_count=Count("variants", distinct=True),
                stock_total=Coalesce(Sum("variants__quantity"), 0),
                min_price=Coalesce(Min("variants__price"), Value(Decimal("0.00"))),
            )
        )

        if search_query:
            search_filter = Q(name__icontains=search_query)
            normalized_search_query = search_query.lower()
            if normalized_search_query.startswith("sku-"):
                normalized_search_query = normalized_search_query[4:]

            if normalized_search_query.isdigit():
                numeric_query = int(normalized_search_query)
                search_filter |= Q(pk=numeric_query) | Q(variants__pk=numeric_query)
            products_queryset = products_queryset.filter(search_filter).distinct()

        if selected_category.isdigit():
            products_queryset = products_queryset.filter(category_id=int(selected_category))

        if selected_stock_filter == "in_stock":
            products_queryset = products_queryset.filter(stock_total__gt=0)
        elif selected_stock_filter == "low_stock":
            products_queryset = products_queryset.filter(stock_total__gt=0, stock_total__lt=5)
        elif selected_stock_filter == "out_of_stock":
            products_queryset = products_queryset.filter(stock_total=0)

        products_queryset = products_queryset.order_by(*self.SORT_OPTIONS[selected_sort])
        products = list(products_queryset)
        for product in products:
            product.preview_image = next(iter(product.images.all()), None)
            product.sku = f"SKU-{product.pk}"
            product.variant_label = _format_variant_label(product.variant_count)
            stock_total = int(product.stock_total or 0)
            product.stock_total = stock_total
            product.stock_state, product.stock_label = _resolve_stock_state(stock_total)

        context["products"] = products
        context["categories"] = Category.objects.annotate(product_count=Count("products")).order_by("name")
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
    def _apply_status_filter(queryset, status_filter: str):
        if status_filter == "new":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.NEW)
        if status_filter == "processing":
            return queryset.filter(fulfillment_status__in=(Order.FulfillmentStatus.PACKING, Order.FulfillmentStatus.SHIPPED))
        if status_filter == "ready":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.RESERVED)
        if status_filter == "issued":
            return queryset.filter(fulfillment_status=Order.FulfillmentStatus.DELIVERED)
        if status_filter == "cancelled":
            return queryset.filter(
                Q(fulfillment_status=Order.FulfillmentStatus.CANCELLED) | Q(status=Order.Status.CANCELLED)
            )
        return queryset

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
        status_filter = self.request.GET.get("status", "all").strip() or "all"
        if status_filter not in {"all", *DASHBOARD_ORDER_STATUS_KEYS}:
            status_filter = "all"

        search_query = self.request.GET.get("q", "").strip()
        orders_queryset = Order.objects.select_related("user").annotate(items_count=Count("items")).order_by("-created_at")

        if search_query:
            orders_queryset = orders_queryset.filter(Q(number__icontains=search_query) | Q(email__icontains=search_query))

        orders_queryset = self._apply_status_filter(orders_queryset, status_filter)
        orders = list(orders_queryset)
        for order in orders:
            dashboard_status_key = _get_dashboard_order_status_key(order)
            dashboard_status_meta = DASHBOARD_ORDER_STATUS_META[dashboard_status_key]
            order.dashboard_status_key = dashboard_status_key
            order.dashboard_status_label = dashboard_status_meta["label"]
            order.dashboard_status_badge = dashboard_status_meta["badge_class"]

        context["orders"] = orders
        context["current_status_filter"] = status_filter
        context["search_query"] = search_query
        context["status_filters"] = self._build_status_filter_links(search_query)
        return context


class DashboardOrderDetailView(ModeratorRequiredMixin, DetailView):
    model = Order
    template_name = "dashboard/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("user").prefetch_related("items")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard_status_key = _get_dashboard_order_status_key(self.object)
        dashboard_status_meta = DASHBOARD_ORDER_STATUS_META[dashboard_status_key]

        context["items"] = self.object.items.order_by("pk")
        context["status_choices"] = DASHBOARD_ORDER_STATUS_CHOICES
        context["current_status_key"] = dashboard_status_key
        context["current_status_label"] = dashboard_status_meta["label"]
        context["current_status_badge"] = dashboard_status_meta["badge_class"]
        return context


class DashboardOrderStatusUpdateView(ModeratorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, pk=self.kwargs["pk"])
        next_status = request.POST.get("status", "").strip()
        if next_status not in DASHBOARD_ORDER_STATUS_KEYS:
            return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))

        _apply_dashboard_order_status(order, next_status)
        order.save(update_fields=["fulfillment_status", "status", "cancelled_at", "updated_at"])
        return HttpResponseRedirect(reverse("store:dashboard_order_detail", kwargs={"pk": order.pk}))


class WarehouseProductCreateView(ModeratorRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "dashboard/product_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Добавить товар"
        context["submit_label"] = "Создать товар"
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.pk})


class WarehouseProductDeleteView(ModeratorRequiredMixin, DeleteView):
    model = Product
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"
    success_url = reverse_lazy("store:warehouse_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Удалить товар"
        context["cancel_url"] = reverse("store:warehouse_product_manage", kwargs={"pk": self.object.pk})
        context["warning_text"] = "Товар и все его варианты будут удалены со склада."
        return context


class WarehouseCategoryCreateView(ModeratorRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "dashboard/category_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Создать категорию"
        context["submit_label"] = "Создать категорию"
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
        context["page_title"] = "Редактировать категорию"
        context["submit_label"] = "Сохранить"
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
        context["page_title"] = "Удалить категорию"
        context["cancel_url"] = reverse("store:warehouse_dashboard")
        context["warning_text"] = "Если в категории есть товары, они также будут удалены."
        return context


class WarehouseProductManageView(ModeratorRequiredMixin, DetailView):
    model = Product
    template_name = "dashboard/product_manage.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.select_related("category").prefetch_related("images", "variants__image")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        product_form = ProductForm(request.POST, instance=self.object)
        if product_form.is_valid():
            product_form.save()
            return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": self.object.pk}))

        context = self.get_context_data(product_form=product_form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        variants = list(self.object.variants.order_by("size", "color", "pk"))
        for variant in variants:
            variant.stock_form = VariantStockForm(instance=variant)

        context["product_form"] = kwargs.get("product_form") or ProductForm(instance=self.object)
        context["variants"] = variants
        context["images"] = self.object.images.order_by("-is_primary", "-created_at")
        return context


class WarehouseVariantCreateView(ModeratorRequiredMixin, CreateView):
    model = ProductVariant
    form_class = ProductVariantForm
    template_name = "dashboard/variant_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product, pk=self.kwargs["product_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.product
        return kwargs

    def form_valid(self, form):
        form.instance.product = self.product
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.product
        context["page_title"] = "Добавить вариант товара"
        context["submit_label"] = "Создать вариант"
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk})


class WarehouseVariantUpdateView(ModeratorRequiredMixin, UpdateView):
    model = ProductVariant
    form_class = ProductVariantForm
    template_name = "dashboard/variant_form.html"
    context_object_name = "variant"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.object.product
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.object.product
        context["page_title"] = "Редактировать вариант"
        context["submit_label"] = "Сохранить"
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})


class WarehouseVariantDeleteView(ModeratorRequiredMixin, DeleteView):
    model = ProductVariant
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Удалить вариант"
        context["cancel_url"] = reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})
        context["warning_text"] = "Остаток этого варианта будет удалён со склада."
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})


class WarehouseVariantStockUpdateView(ModeratorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        variant = get_object_or_404(ProductVariant, pk=self.kwargs["pk"])
        form = VariantStockForm(request.POST, instance=variant)
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse("store:warehouse_product_manage", kwargs={"pk": variant.product.pk}))


class WarehouseImageCreateView(ModeratorRequiredMixin, CreateView):
    model = ProductImage
    form_class = ProductImageForm
    template_name = "dashboard/image_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product, pk=self.kwargs["product_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.product = self.product
        if form.cleaned_data.get("is_primary"):
            self.product.images.update(is_primary=False)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.product
        context["page_title"] = "Добавить изображение"
        context["submit_label"] = "Загрузить"
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.product.pk})


class WarehouseImageDeleteView(ModeratorRequiredMixin, DeleteView):
    model = ProductImage
    template_name = "dashboard/confirm_delete.html"
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Удалить изображение"
        context["cancel_url"] = reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})
        context["warning_text"] = "При удалении изображение будет отвязано от связанных вариантов товара."
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})
