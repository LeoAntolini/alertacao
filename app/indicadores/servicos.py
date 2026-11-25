"""Indicadores I1 a I8 e contagens de apoio (seção 13 do Documento-Base, RF08)."""
from collections import Counter
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from alertas.choices import StatusAlerta, StatusTarefa
from alertas.models import Alerta, Tarefa
from chamados.models import Chamado, ResolvidoPor, StatusChamado
from notificacoes.models import CanalNotificacao, Notificacao, StatusEnvio
from pontos.models import PontoDeRisco, StatusPonto
from usuarios.models import Papel, Usuario


def _horas(delta):
    return delta.total_seconds() / 3600


def _media(valores):
    return sum(valores) / len(valores) if valores else None


def _percentual(numerador, denominador):
    return numerador / denominador * 100 if denominador else None


def calcular(dias=30, agora=None):
    """Calcula os indicadores para os últimos `dias` dias. Valor None = sem dados no período."""
    agora = agora or timezone.now()
    desde = agora - timedelta(days=dias)

    alertas = list(
        Alerta.objects.filter(
            status__in=[StatusAlerta.PUBLICADO, StatusAlerta.ENCERRADO],
            publicado_em__gte=desde, publicado_em__lte=agora,
        ).select_related("regiao")
    )

    # I1: antecedência média dos alertas (h)
    i1 = _media([_horas(a.janela_inicio - a.publicado_em) for a in alertas])

    # I2: taxa de adesão ao plano = concluídas ÷ (geradas − dispensadas)
    tarefas = list(Tarefa.objects.filter(alerta__in=alertas))
    dispensadas = sum(1 for t in tarefas if t.status == StatusTarefa.DISPENSADA)
    concluidas = sum(1 for t in tarefas if t.status == StatusTarefa.CONCLUIDA)
    i2 = _percentual(concluidas, len(tarefas) - dispensadas)

    # I3: pontos ativos na publicação que ficaram resolvidos até o início previsto do evento
    base = tratados = 0
    for alerta in alertas:
        ativos = PontoDeRisco.objects.filter(regiao=alerta.regiao, criado_em__lte=alerta.publicado_em).filter(
            Q(resolvido_em__isnull=True) | Q(resolvido_em__gt=alerta.publicado_em)
        )
        base += ativos.count()
        tratados += ativos.filter(resolvido_em__isnull=False, resolvido_em__lte=alerta.janela_inicio).count()
    i3 = _percentual(tratados, base)

    # I4: tempo médio de resolução dos chamados (h), entre o encaminhamento e a resolução
    resolvidos = Chamado.objects.filter(
        status=StatusChamado.RESOLVIDO, resolvido_em__gte=desde, resolvido_em__lte=agora, encaminhado_em__isnull=False
    )
    i4 = _media([_horas(c.resolvido_em - c.encaminhado_em) for c in resolvidos])

    # I5: taxa de retorno do destinatário
    encaminhados = list(
        Chamado.objects.filter(
        	encaminhado_em__gte=desde,
        	encaminhado_em__lte=agora,
    	)
    )
    com_retorno = sum(
        1 for c in encaminhados
        if c.em_atendimento_em or c.resolvido_por == ResolvidoPor.DESTINATARIO or c.status == StatusChamado.NAO_PROCEDE
    )
    i5 = _percentual(com_retorno, len(encaminhados))

    # I6: cobertura de notificação = moradores notificados ÷ moradores da região (hoje), por alerta
    notificados = moradores = 0
    for alerta in alertas:
        moradores += Usuario.objects.filter(papel=Papel.MORADOR, regiao=alerta.regiao, is_active=True).count()
        notificados += (
            Notificacao.objects.filter(alerta=alerta, canal=CanalNotificacao.APP, status=StatusEnvio.ENTREGUE)
            .values("usuario").distinct().count()
        )
    i6 = _percentual(notificados, moradores)

    # I7: concentração de riscos = pontos ativos por região e categoria
    contagem = Counter(
        PontoDeRisco.objects.filter(status=StatusPonto.ATIVO).values_list("regiao__nome", "categoria")
    )
    i7 = [{"regiao": r, "categoria": c, "n": n} for (r, c), n in sorted(contagem.items())]

    # I8: tempo médio entre a publicação do alerta e a conclusão da tarefa (h)
    feitas = Tarefa.objects.filter(
        status=StatusTarefa.CONCLUIDA, concluida_em__gte=desde, concluida_em__lte=agora
    ).select_related("alerta")
    i8 = _media([_horas(t.concluida_em - t.alerta.publicado_em) for t in feitas if t.alerta.publicado_em])

    return {
        "dias": dias, "desde": desde,
        "i1": i1, "i2": i2, "i3": i3, "i4": i4, "i5": i5, "i6": i6, "i7": i7, "i8": i8,
        "alertas_publicados": len(alertas),
        "tarefas_concluidas": Tarefa.objects.filter(
            status=StatusTarefa.CONCLUIDA, concluida_em__gte=desde, concluida_em__lte=agora
        ).count(),
        "chamados_abertos": Chamado.objects.filter(
    		encaminhado_em__gte=desde,
    		encaminhado_em__lte=agora,
	).count(),
    }
