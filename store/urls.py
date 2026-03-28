from django.urls import path

from store.views.views_product import MainView, ProductListView, ProductDetailsView, ProductUpdateView, \
    ProductDeleteView

app_name = "store"

urlpatterns = [
    path("", MainView.as_view(), name="base"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/<int:pk>/", ProductDetailsView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", ProductUpdateView.as_view(), name="product_edit"),
    path("products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product_delete"),
]
