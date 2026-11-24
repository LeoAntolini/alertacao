import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from alertas.models import Tarefa
from pontos.models import PontoDeRisco, StatusPonto

from .forms import AcionarForm, AjudaTarefaForm
from .models import Chamado
from .servicos import (
    ACOES_DO_DESTINATARIO, LINK_SP156, abrir_chamado, chamado_do_token, confirmar_resolucao, registrar_acao,
)


def _avisar_resultado(request, enviado):
    if enviado:
        messages.success(request, "Pedido encaminhado ao órgão responsável por e-mail.")
    else:
        messages.warning(request, "Pedido registrado, mas o e-mail ainda não saiu. Ele será reenviado.")


@login_required
def acionar_ponto(request, pk):
    """RF07: 'Acionar órgão' em um ponto de risco da região do morador."""
    ponto = get_object_or_404(PontoDeRisco, pk=pk, regiao_id=request.user.regiao_id, status=StatusPonto.ATIVO)
    if request.method == "POST":
        form = AcionarForm(request.POST)
        if form.is_valid():
            try:
                _, enviado = abrir_chamado(
                    request.user, ponto, form.cleaned_data["descricao"], form.cleaned_data["risco_iminente"]
                )
            except ValidationError as erro:
                messages.error(request, "; ".join(erro.messages))
            else:
                _avisar_resultado(request, enviado)
                return redirect("meus_chamados")
    else:
        form = AcionarForm(initial={"descricao": ponto.descricao})
    return render(request, "chamados/acionar.html", {"form": form, "ponto": ponto, "link_sp156": LINK_SP156})


@login_required
def pedir_ajuda(request, pk):
    """RF07: 'Preciso de ajuda' em uma tarefa: relata o risco no mapa e aciona o órgão."""
    tarefa = get_object_or_404(Tarefa.objects.select_related("modelo", "alerta"), pk=pk, usuario=request.user)
    regiao = request.user.regiao
    if regiao is None:
        raise Http404
    if request.method == "POST":
        form = AjudaTarefaForm(request.POST, regiao=regiao)
        if form.is_valid():
            dados = form.cleaned_data
            try:
                with transaction.atomic():
                    ponto = PontoDeRisco.objects.create(
                        autor=request.user, regiao=regiao, categoria=dados["categoria"],
                        descricao=dados["descricao"], localizacao=form.ponto, endereco=dados.get("endereco", ""),
                        precisao_metros=dados.get("precisao_metros"),
                    )
                    _, enviado = abrir_chamado(
                        request.user, ponto, dados["descricao"], dados["risco_iminente"], tarefa=tarefa
                    )
            except ValidationError as erro:
                messages.error(request, "; ".join(erro.messages))
            else:
                _avisar_resultado(request, enviado)
                return redirect("meus_chamados")
    else:
        inicial = {"categoria": tarefa.modelo.categoria} if tarefa.modelo.categoria else {}
        form = AjudaTarefaForm(initial=inicial, regiao=regiao)
    contexto = {
        "form": form, "tarefa": tarefa, "regiao": regiao, "link_sp156": LINK_SP156,
        "regiao_geojson": json.loads(regiao.geometria.geojson), "tile_url": settings.MAP_TILE_URL,
    }
    return render(request, "chamados/ajuda_tarefa.html", contexto)


@login_required
def meus_chamados(request):
    """RF19: status e histórico dos chamados que o morador abriu."""
    chamados = Chamado.objects.filter(autor=request.user).select_related("ponto", "destinatario")
    return render(request, "chamados/lista.html", {"chamados": chamados, "link_sp156": LINK_SP156})


@login_required
@require_POST
def confirmar(request, pk):
    """RF20."""
    chamado = get_object_or_404(Chamado, pk=pk, autor=request.user)
    try:
        confirmar_resolucao(chamado, request.user)
    except ValidationError as erro:
        messages.error(request, "; ".join(erro.messages))
    else:
        messages.success(request, "Obrigado! O chamado e o ponto de risco foram marcados como resolvidos.")
    return redirect("meus_chamados")


def acao_por_link(request, token):
    """RF18: página do link seguro do destinatário, sem login (RN08)."""
    chamado = chamado_do_token(token)
    if chamado is None:
        return render(request, "chamados/indisponivel.html", status=410)
    mensagem = ""
    if request.method == "POST":
        acao = request.POST.get("acao", "")
        if acao not in ACOES_DO_DESTINATARIO:
            return HttpResponse("Ação desconhecida.", status=400)
        try:
            registrar_acao(chamado, acao)
        except ValidationError as erro:
            mensagem = "; ".join(erro.messages)
        else:
            mensagem = "Obrigado! O status do chamado foi atualizado."
    ponto = chamado.ponto
    lat, lon = ponto.localizacao.y, ponto.localizacao.x
    contexto = {
        "chamado": chamado, "ponto": ponto, "mensagem": mensagem, "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
        "mapa": f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}",
        "encerrado": chamado.finalizado,
    }
    return render(request, "chamados/acao.html", contexto)
