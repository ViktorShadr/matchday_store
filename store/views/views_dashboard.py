from django.contrib import messages
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from store.forms import CategoryForm, ProductForm, ProductImageForm, ProductVariantForm, VariantStockForm
from store.mixins import ModeratorRequiredMixin
from store.models import Category, Product, ProductImage, ProductVariant


class DashboardHomeView(ModeratorRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product_count"] = Product.objects.count()
        context["category_count"] = Category.objects.count()
        context["variant_count"] = ProductVariant.objects.count()
        context["total_stock"] = ProductVariant.objects.aggregate(total=Coalesce(Sum("quantity"), 0))["total"]
        context["recent_products"] = Product.objects.select_related("category").order_by("-created_at")[:5]
        context["largest_categories"] = Category.objects.annotate(product_count=Count("products")).order_by(
            "-product_count", "name"
        )[:5]
        return context


class WarehouseDashboardView(ModeratorRequiredMixin, TemplateView):
    template_name = "dashboard/warehouse.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = (
            Product.objects.select_related("category")
            .annotate(variant_count=Count("variants"), stock_total=Coalesce(Sum("variants__quantity"), 0))
            .order_by("name")
        )
        context["categories"] = Category.objects.annotate(product_count=Count("products")).order_by("name")
        return context


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


class WarehouseProductUpdateView(ModeratorRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "dashboard/product_form.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Редактировать товар"
        context["submit_label"] = "Сохранить"
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        variants = list(self.object.variants.order_by("size", "color", "pk"))
        for variant in variants:
            variant.stock_form = VariantStockForm(instance=variant)

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
        context["warning_text"] = "Изображение нельзя удалить, пока оно используется в вариантах товара."
        return context

    def get_success_url(self):
        return reverse("store:warehouse_product_manage", kwargs={"pk": self.object.product.pk})

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if ProductVariant.objects.filter(image=self.object).exists():
            messages.error(request, "Нельзя удалить изображение: оно используется в вариантах товара.")
            return HttpResponseRedirect(self.get_success_url())
        return super().post(request, *args, **kwargs)
