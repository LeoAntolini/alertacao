from django.urls import path

from . import views

urlpatterns = [
    path("notificacoes/", views.lista, name="notificacoes"),
]
