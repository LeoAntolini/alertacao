from django.urls import path

from . import views

urlpatterns = [
    path("pontos/<uuid:pk>/acionar/", views.acionar_ponto, name="chamado_acionar_ponto"),
    path("tarefas/<uuid:pk>/ajuda/", views.pedir_ajuda, name="chamado_pedir_ajuda"),
    path("chamados/", views.meus_chamados, name="meus_chamados"),
    path("chamados/<uuid:pk>/resolvido/", views.confirmar, name="chamado_confirmar"),
    path("chamados/acao/<str:token>/", views.acao_por_link, name="chamado_acao"),
]
