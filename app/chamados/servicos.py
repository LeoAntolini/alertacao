import secrets

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from alertas.choices import StatusTarefa
from pontos.models import StatusPonto

from .models import (
    PRAZO_LINK, PRAZO_SEM_RETORNO, STATUS_FINAIS, Chamado, Destinatario, ResolvidoPor, StatusChamado,
)

ACOES_DO_DESTINATARIO = {
    "EM_ATENDIMENTO": StatusChamado.EM_ATENDIMENTO,
    "RESOLVIDO": StatusChamado.RESOLVIDO,
    "NAO_PROCEDE": StatusChamado.NAO_PROCEDE,
}
LINK_SP156 = "https://sp156.prefeitura.sp.gov.br/portal/servicos"
AVISO_EMAIL = (
    "Este pedido foi gerado pelo AlertAção, um projeto acadêmico de moradores, e não substitui o registro oficial "
    f"(Central 156 ou {LINK_SP156})."
)


def rotear(categoria):
    """Destinatário que atende a categoria (D04, RF17)."""
    for destinatario in Destinatario.objects.order_by("nome"):
        if destinatario.atende(categoria):
            return destinatario
    return None


def _montar_email(chamado, token):
    ponto = chamado.ponto
    lat, lon = ponto.localizacao.y, ponto.localizacao.x
    urgente = "URGENTE: " if chamado.risco_iminente else ""
    assunto = f"[AlertAção] {urgente}Pedido de ajuda: {ponto.get_categoria_display()} em {ponto.regiao.nome}"
    link = settings.SITE_URL.rstrip("/") + reverse("chamado_acao", args=[token])
    mapa = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"
    corpo = (
        "Pedido de ajuda enviado pelo AlertAção\n\n"
        f"Categoria: {ponto.get_categoria_display()}\n"
        f"Região: {ponto.regiao.nome}\n"
        f"Risco iminente: {'SIM' if chamado.risco_iminente else 'não informado'}\n"
        f"Descrição do ponto de risco: {ponto.descricao}\n"
	f"Descrição do pedido de ajuda: {chamado.descricao}\n"
        f"Referência: {ponto.endereco or 'não informada'}\n"
        f"Localização: {lat:.6f}, {lon:.6f}\n"
        f"Mapa: {mapa}\n"
        "Foto: não há foto anexada.\n\n"
        f"Para informar o andamento, use este link (sem login, válido por 30 dias):\n{link}\n\n"
        f"{AVISO_EMAIL}\n"
    )
    return assunto, corpo


def encaminhar(chamado, agora=None):
    """Envia o e-mail ao destinatário com um link novo. Retorna True se o provedor aceitou (RF17).

    Se falhar, o chamado continua ABERTO e pode ser reenviado (o token só é guardado como hash).
    """
    agora = agora or timezone.now()
    token = secrets.token_urlsafe(32)
    chamado.token_hash = Chamado.hash_do_token(token)
    chamado.token_expira_em = agora + PRAZO_LINK
    chamado.save(update_fields=["token_hash", "token_expira_em"])
    assunto, corpo = _montar_email(chamado, token)
    try:
        EmailMessage(assunto, corpo, to=[chamado.destinatario.email]).send()
    except Exception:
        return False
    chamado.status = StatusChamado.ENCAMINHADO
    chamado.encaminhado_em = timezone.now()
    chamado.save(update_fields=["status", "encaminhado_em"])
    return True


def abrir_chamado(autor, ponto, descricao, risco_iminente=False, tarefa=None, agora=None):
    """RF07: cria o chamado ABERTO, escala a tarefa de origem (se houver) e encaminha por e-mail (RF17).

    Retorna (chamado, enviado).
    """
    agora = agora or timezone.now()
    if autor.regiao_id != ponto.regiao_id:
        raise PermissionDenied("O ponto de risco não é da sua região.")
    if ponto.status != StatusPonto.ATIVO:
        raise ValidationError("Só pontos de risco ativos podem receber chamado.")
    if Chamado.objects.filter(ponto=ponto).exclude(status__in=STATUS_FINAIS).exists():
        raise ValidationError("Já existe um chamado em andamento para este ponto de risco.")
    if tarefa is not None:
        if tarefa.usuario_id != autor.pk:
            raise PermissionDenied("A tarefa não é sua.")
        if tarefa.status != StatusTarefa.PENDENTE:
            raise ValidationError("Só tarefas pendentes podem pedir ajuda.")
    destinatario = rotear(ponto.categoria)
    if destinatario is None:
        raise ValidationError("Não há órgão cadastrado para esta categoria de risco.")

    with transaction.atomic():
        chamado = Chamado.objects.create(
            autor=autor, ponto=ponto, tarefa=tarefa, destinatario=destinatario, descricao=descricao,
            risco_iminente=risco_iminente,
            token_hash=Chamado.hash_do_token(secrets.token_urlsafe(32)),  # provisório; encaminhar() gera o definitivo
            token_expira_em=agora + PRAZO_LINK,
        )
        if tarefa is not None:
            tarefa.escalar(agora)
    enviado = encaminhar(chamado, agora)
    return chamado, enviado


def chamado_do_token(token, agora=None):
    """Chamado do link seguro, ou None se o link for inválido, expirado ou o chamado já estiver encerrado (RN08)."""
    agora = agora or timezone.now()
    chamado = (
        Chamado.objects.select_related("ponto", "ponto__regiao", "destinatario")
        .filter(token_hash=Chamado.hash_do_token(token))
        .first()
    )
    if chamado is None or chamado.token_expira_em < agora or chamado.finalizado:
        return None
    return chamado


def _resolver_ponto(chamado, agora):
    if chamado.ponto.status == StatusPonto.ATIVO:
        chamado.ponto.resolver(agora)


def registrar_acao(chamado, acao, agora=None):
    """RF18: o destinatário informa em atendimento, resolvido ou não procede."""
    agora = agora or timezone.now()
    if acao not in ACOES_DO_DESTINATARIO:
        raise ValidationError("Ação desconhecida.")
    if chamado.finalizado:
        raise ValidationError("Este chamado já foi encerrado.")
    novo = ACOES_DO_DESTINATARIO[acao]
    with transaction.atomic():
        chamado.status = novo
        if novo == StatusChamado.EM_ATENDIMENTO:
            chamado.em_atendimento_em = agora
        elif novo == StatusChamado.RESOLVIDO:
            chamado.resolvido_em = agora
            chamado.resolvido_por = ResolvidoPor.DESTINATARIO
            _resolver_ponto(chamado, agora)
        chamado.save()


def confirmar_resolucao(chamado, usuario, agora=None):
    """RF20: o morador autor confirma que o problema foi resolvido."""
    agora = agora or timezone.now()
    if chamado.autor_id != usuario.pk:
        raise PermissionDenied("Só quem abriu o chamado pode confirmar a resolução.")
    if chamado.finalizado:
        raise ValidationError("Este chamado já foi encerrado.")
    with transaction.atomic():
        chamado.status = StatusChamado.RESOLVIDO
        chamado.resolvido_em = agora
        chamado.resolvido_por = ResolvidoPor.MORADOR
        chamado.save()
        _resolver_ponto(chamado, agora)


def verificar_sem_retorno(agora=None):
    """RN09: ENCAMINHADO ou EM_ATENDIMENTO há mais de 72 h passa a SEM_RETORNO. Retorna quantos mudaram."""
    agora = agora or timezone.now()
    limite = agora - PRAZO_SEM_RETORNO
    return Chamado.objects.filter(
        status__in=[StatusChamado.ENCAMINHADO, StatusChamado.EM_ATENDIMENTO], encaminhado_em__lt=limite
    ).update(status=StatusChamado.SEM_RETORNO)


def reenviar_abertos():
    """Reenvia por e-mail os chamados que ficaram ABERTOS porque o envio falhou. Retorna (enviados, falhas)."""
    enviados = falhas = 0
    for chamado in Chamado.objects.filter(status=StatusChamado.ABERTO).select_related("ponto", "ponto__regiao", "destinatario"):
        if encaminhar(chamado):
            enviados += 1
        else:
            falhas += 1
    return enviados, falhas
