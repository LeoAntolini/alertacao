from django.urls import path

from . import views

urlpatterns = [
    path("alertas/<uuid:pk>/", views.detalhe, name="alerta_detalhe"),
    path("tarefas/<uuid:pk>/concluir/", views.concluir_tarefa, name="tarefa_concluir"),
    path("tarefas/<uuid:pk>/dispensar/", views.dispensar_tarefa, name="tarefa_dispensar"),
]
