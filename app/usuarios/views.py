from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from regioes.models import Regiao

from .forms import CadastroForm
from .models import Papel, Usuario


@login_required
def inicio(request):
    return render(request, "usuarios/inicio.html")


def cadastro(request):
    if request.user.is_authenticated:
        return redirect("inicio")

    if request.method == "POST":
        form = CadastroForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            usuario = Usuario.objects.create_user(
                username=dados["email"],
                email=dados["email"],
                password=dados["senha1"],
                nome=dados["nome"],
                papel=Papel.MORADOR,
                regiao=form.regiao,
                ponto_referencia=form.ponto,
                endereco=dados["endereco"],
                precisao_metros=dados.get("precisao_metros"),
                consentimento_em=timezone.now(),
            )
            login(request, usuario)
            return redirect("inicio")
    else:
        form = CadastroForm()

    regioes = [
        {"nome": r.nome, "lat": r.ponto_representativo.y, "lon": r.ponto_representativo.x}
        for r in Regiao.objects.all()
    ]
    contexto = {
        "form": form,
        "regioes": regioes,
        "tile_url": settings.MAP_TILE_URL,
        "demo": settings.DEMO_MODE,
    }
    return render(request, "usuarios/cadastro.html", contexto)
