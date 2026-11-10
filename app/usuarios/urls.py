from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("cadastro/", views.cadastro, name="cadastro"),
    path(
        "entrar/",
        LoginView.as_view(
            template_name="usuarios/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("sair/", LogoutView.as_view(), name="logout"),
]
