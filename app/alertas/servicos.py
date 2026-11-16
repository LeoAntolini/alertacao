from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from usuarios.models import Papel, Usuario

from .choices import CATEGORIAS_SEM_TAREFA, StatusAlerta
from .models import ModeloTarefa, Tarefa


@dataclass
class ResultadoPublicacao:
    moradores: int
    tarefas: int


def publicar_alerta(alerta, responsavel, agora=None):
    """Publica um rascunho e gera o plano de prevenção (RF04 e RF05; RN02, RN03 e RN06).

    A notificação dos moradores (RF14) entra em um passo seguinte.
    """
    agora = agora or timezone.now()
    if responsavel.papel != Papel.RESPONSAVEL_SISTEMA:
        raise PermissionDenied("Só o Responsável pelo Sistema pode publicar alertas.")
    if alerta.status != StatusAlerta.RASCUNHO:
        raise ValidationError("Só alertas em rascunho podem ser publicados.")
    alerta.validar_janela(agora)

    with transaction.atomic():
        alerta.status = StatusAlerta.PUBLICADO
        alerta.publicado_em = agora
        alerta.publicado_por = responsavel
        alerta.ultimo_estagio_notificado = alerta.estagio(agora)
        alerta.save()

        moradores = list(
            Usuario.objects.filter(papel=Papel.MORADOR, regiao=alerta.regiao, is_active=True)
        )
        modelos = list(
            ModeloTarefa.objects.filter(evento=alerta.evento, ativo=True).exclude(
                categoria__in=CATEGORIAS_SEM_TAREFA
            )
        )
        tarefas = [Tarefa(alerta=alerta, modelo=m, usuario=u) for u in moradores for m in modelos]
        Tarefa.objects.bulk_create(tarefas)

    return ResultadoPublicacao(moradores=len(moradores), tarefas=len(tarefas))
