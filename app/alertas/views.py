from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .choices import StatusAlerta, StatusTarefa
from .models import Alerta, Tarefa
from .servicos import encerrar_alertas
from .utils import formatar_duracao


@login_required
def detalhe(request, pk):
    """RF15: alerta ativo da região do morador, com o plano de prevenção dele."""
    encerrar_alertas()  # RF21: o estado também é avaliado na leitura
    alerta = get_object_or_404(
        Alerta.objects.select_related("regiao"),
        pk=pk, status=StatusAlerta.PUBLICADO, regiao_id=request.user.regiao_id,
    )
    agora = timezone.now()
    tarefas = list(
        alerta.tarefas.filter(usuario=request.user).select_related("modelo").order_by("modelo__titulo")
    )
    dispensadas = sum(1 for t in tarefas if t.status == StatusTarefa.DISPENSADA)
    concluidas = sum(1 for t in tarefas if t.status == StatusTarefa.CONCLUIDA)
    contexto = {
        "alerta": alerta,
        "estagio": alerta.estagio(agora),
        "restante_texto": formatar_duracao(alerta.janela_inicio - agora),
        "tarefas": tarefas,
        "concluidas": concluidas,
        "total": len(tarefas) - dispensadas,  # RF16: dispensadas ficam fora do denominador
    }
    return render(request, "alertas/detalhe.html", contexto)


def _mudar_tarefa(request, pk, metodo, mensagem_ok):
    tarefa = get_object_or_404(Tarefa, pk=pk, usuario=request.user)  # só o dono (RN05)
    try:
        getattr(tarefa, metodo)()
    except ValidationError as erro:
        messages.error(request, "; ".join(erro.messages))
    else:
        messages.success(request, mensagem_ok)
    return redirect("alerta_detalhe", pk=tarefa.alerta_id)


@login_required
@require_POST
def concluir_tarefa(request, pk):
    """RF06."""
    return _mudar_tarefa(request, pk, "concluir", "Tarefa concluída.")


@login_required
@require_POST
def dispensar_tarefa(request, pk):
    """RF16."""
    return _mudar_tarefa(request, pk, "dispensar", "Tarefa marcada como “não se aplica”.")
