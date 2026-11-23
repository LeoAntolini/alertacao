from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("alertas.urls")),
    path("", include("usuarios.urls")),
    path("", include("notificacoes.urls")),
]
