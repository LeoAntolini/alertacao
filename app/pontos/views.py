import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from alertas.choices import CategoriaRisco

from .forms import PontoForm
from .models import PontoDeRisco, StatusPonto


def _regiao_ou_none(request):
    regiao = request.user.regiao
    if regiao is None:
        messages.error(request, "Seu usuário não está ligado a uma região.")
    return regiao


def _contexto_mapa(regiao):
    return {
        "regiao": regiao,
        "regiao_geojson": json.loads(regiao.geometria.geojson),
        "tile_url": settings.MAP_TILE_URL,
    }


@login_required
def mapa(request):
    """RF03: pontos ATIVOS da região do morador, com filtro por categoria."""
    regiao = _regiao_ou_none(request)
    if regiao is None:
        return redirect("inicio")
    categoria = request.GET.get("categoria", "")
    pontos = PontoDeRisco.objects.filter(regiao=regiao, status=StatusPonto.ATIVO)
    if categoria in CategoriaRisco.values:
        pontos = pontos.filter(categoria=categoria)
    dados = [
        {
            "id": str(p.pk),
            "lat": p.localizacao.y,
            "lon": p.localizacao.x,
            "categoria": p.get_categoria_display(),
            "descricao": p.descricao,
            "endereco": p.endereco,
            "quando": timezone.localtime(p.criado_em).strftime("%d/%m/%Y"),
        }
        for p in pontos  # sem autoria (RN10)
    ]
    contexto = _contexto_mapa(regiao)
    contexto.update({
        "pontos": dados,
        "categorias": CategoriaRisco.choices,
        "filtro": categoria if categoria in CategoriaRisco.values else "",
    })
    return render(request, "pontos/mapa.html", contexto)


@login_required
def relatar(request):
    """RF02: registra um ponto de risco dentro da região do morador (RN15)."""
    regiao = _regiao_ou_none(request)
    if regiao is None:
        return redirect("inicio")
    if request.method == "POST":
        form = PontoForm(request.POST, regiao=regiao)
        if form.is_valid():
            dados = form.cleaned_data
            PontoDeRisco.objects.create(
                autor=request.user, regiao=regiao, categoria=dados["categoria"], descricao=dados["descricao"],
                localizacao=form.ponto, endereco=dados.get("endereco", ""),
                precisao_metros=dados.get("precisao_metros"),
            )
            messages.success(request, "Risco registrado. Obrigado por avisar a vizinhança.")
            return redirect("mapa")
    else:
        form = PontoForm(regiao=regiao)
    contexto = _contexto_mapa(regiao)
    contexto["form"] = form
    return render(request, "pontos/relatar.html", contexto)
