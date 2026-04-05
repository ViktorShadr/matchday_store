from django.urls import path

from store.views.views_product import (
    MainView,
    ProductListView,
    ProductDetailsView,
    ProductUpdateView,
    ProductDeleteView,
    ProductCreateView,
)
from store.views.views_category import (
    CategoryListView,
    CategoryDetailView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDeleteView,
)
from store.views.views_cart import AddToCartView, UpdateCartView, RemoveFromCartView
from store.views.views_cart_page import CartView

app_name = "store"

urlpatterns = [
    path("", MainView.as_view(), name="base"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/create/", ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", ProductDetailsView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", ProductUpdateView.as_view(), name="product_edit"),
    path("products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product_delete"),
    path("categories/", CategoryListView.as_view(), name="category_list"),
    path("categories/create/", CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/", CategoryDetailView.as_view(), name="category_detail"),
    path("categories/<int:pk>/edit/", CategoryUpdateView.as_view(), name="category_edit"),
    path("categories/<int:pk>/delete/", CategoryDeleteView.as_view(), name="category_delete"),
    # Корзина
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/add/", AddToCartView.as_view(), name="add_to_cart"),
    path("cart/update/", UpdateCartView.as_view(), name="update_cart"),
    path("cart/remove/", RemoveFromCartView.as_view(), name="remove_from_cart"),
]
