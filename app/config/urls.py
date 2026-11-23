# Conteúdo completo de app/config/urls.py depois da implantação.
# Ele reúne tudo que já foi acrescentado (admin, usuarios, alertas e notificacoes) mais a rota /saude/.
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def saude(request):
    """Verificação de saúde para a hospedagem e para o monitor de disponibilidade (RNF03)."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("saude/", saude, name="saude"),
    path("", include("usuarios.urls")),
    path("", include("alertas.urls")),
    path("", include("notificacoes.urls")),
]
