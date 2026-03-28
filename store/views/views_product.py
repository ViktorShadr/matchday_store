from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Prefetch
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, TemplateView, UpdateView

from store.models import Category, Product, ProductVariant


def _catalog_queryset():
    return Product.objects.select_related("category").prefetch_related(
        "images",
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("image").order_by("price", "id"),
        ),
    )


def _enrich_product(product):
    images = list(product.images.all())
    variants = list(product.variants.all())

    primary_image = next((image for image in images if image.is_primary), None)
    first_image = primary_image or (images[0] if images else None)
    first_variant = variants[0] if variants else None

    product.display_image = first_image.image if first_image else getattr(getattr(first_variant, "image", None), "image", None)
    product.display_price = first_variant.price if first_variant else None
    return product


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class MainView(TemplateView):
    template_name = "main_page/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = Category.objects.order_by("name")
        products = [_enrich_product(product) for product in _catalog_queryset().order_by("-created_at")[:6]]

        context["categories"] = categories
        context["popular_products"] = products
        return context


class ProductListView(ListView):
    model = Product
    template_name = "main_page/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        return [_enrich_product(product) for product in _catalog_queryset().order_by("-created_at")]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.order_by("name")
        return context


class ProductDetailsView(DetailView):
    model = Product
    template_name = "main_page/product_details.html"
    context_object_name = "product"

    def get_queryset(self):
        return _catalog_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = _enrich_product(self.object)

        context["product"] = product
        context["product_images"] = product.images.all()
        context["variants"] = product.variants.all()
        return context


class ProductUpdateView(StaffRequiredMixin, UpdateView):
    model = Product
    template_name = "main_page/product_update.html"
    fields = ["name", "description", "category"]
    context_object_name = "product"

    def get_success_url(self):
        return reverse_lazy("store:product_detail", kwargs={"pk": self.object.pk})


class ProductDeleteView(StaffRequiredMixin, DeleteView):
    model = Product
    template_name = "main_page/product_delete.html"
    context_object_name = "product"
    success_url = reverse_lazy("store:product_list")
