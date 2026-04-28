from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from config.health import healthz_view

urlpatterns = [
    path("healthz/", healthz_view, name="healthz"),
    path("admin/", admin.site.urls),
    path("", include("store.urls", namespace="store")),
    path("", include("orders.urls", namespace="orders")),
    path("users/", include("users.urls", namespace="users")),
]

# Custom error handlers
handler404 = 'store.views.views_legal.error_404_view'
handler500 = 'store.views.views_legal.error_500_view'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
