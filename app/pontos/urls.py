from django.urls import path

from . import views

urlpatterns = [
    path("mapa/", views.mapa, name="mapa"),
    path("pontos/novo/", views.relatar, name="ponto_novo"),
]
