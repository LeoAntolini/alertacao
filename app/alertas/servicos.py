from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from usuarios.models import Papel, Usuario

from notificacoes.servicos import enviar_pendentes, notificar_alerta

from .choices import CATEGORIAS_SEM_TAREFA, StatusAlerta
from .choices import StatusTarefa
from .models import Alerta, ModeloTarefa, Tarefa


@dataclass
class ResultadoPublicacao:
    moradores: int
    tarefas: int
    emails_enviados: int = 0
    emails_com_falha: int = 0


def publicar_alerta(alerta, responsavel, agora=None):
    """Publica um rascunho, gera o plano de prevenção e notifica os moradores (RF04, RF05 e RF14).

    A publicação e o plano ficam salvos mesmo que o envio de e-mail falhe.
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
        notificar_alerta(alerta, moradores, agora)

    enviados, falhas = enviar_pendentes()
    return ResultadoPublicacao(
        moradores=len(moradores), tarefas=len(tarefas), emails_enviados=enviados, emails_com_falha=falhas
    )


def encerrar_alertas(agora=None):
    """RF21: encerra os alertas PUBLICADOS cujo fim já passou e expira as tarefas pendentes deles (RN04).

    Retorna (alertas encerrados, tarefas expiradas). Pode rodar quantas vezes quiser.
    """
    agora = agora or timezone.now()
    vencidos = list(Alerta.objects.filter(status=StatusAlerta.PUBLICADO, janela_fim__lte=agora))
    if not vencidos:
        return 0, 0
    ids = [a.pk for a in vencidos]
    with transaction.atomic():
        Alerta.objects.filter(pk__in=ids).update(status=StatusAlerta.ENCERRADO, encerrado_em=agora)
        expiradas = Tarefa.objects.filter(alerta_id__in=ids, status=StatusTarefa.PENDENTE).update(
            status=StatusTarefa.EXPIRADA, expirada_em=agora
        )
    return len(ids), expiradas
