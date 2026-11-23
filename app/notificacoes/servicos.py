from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.urls import reverse
from django.utils import timezone

from alertas.utils import formatar_duracao

from .models import CanalNotificacao, Notificacao, StatusEnvio, titulo_notificacao

AVISO = (
    "Aviso preventivo comunitário. Não substitui alertas oficiais da Defesa Civil. "
    "Em risco iminente, ligue 199 (Defesa Civil) ou 193 (Bombeiros)."
)


def notificar_alerta(alerta, moradores, agora=None, estagio=None):
    """Registra a notificação na caixa de entrada (ENTREGUE) e deixa o e-mail PENDENTE (RF14).

    Pode rodar de novo para o mesmo estágio sem duplicar (restrição única).
    Retorna quantos moradores foram notificados.
    """
    agora = agora or timezone.now()
    estagio = estagio or alerta.estagio(agora)
    registros = []
    for morador in moradores:
        registros.append(Notificacao(
            alerta=alerta, usuario=morador, canal=CanalNotificacao.APP, estagio=estagio,
            status=StatusEnvio.ENTREGUE, enviada_em=agora, entregue_em=agora,
        ))
        if morador.email:
            registros.append(Notificacao(
                alerta=alerta, usuario=morador, canal=CanalNotificacao.EMAIL, estagio=estagio,
            ))
    Notificacao.objects.bulk_create(registros, ignore_conflicts=True)
    return len(moradores)


def _montar_email(notificacao, agora):
    alerta = notificacao.alerta
    titulo = titulo_notificacao(alerta, notificacao.estagio)
    inicio = timezone.localtime(alerta.janela_inicio).strftime("%d/%m/%Y %H:%M")
    fim = timezone.localtime(alerta.janela_fim).strftime("%d/%m/%Y %H:%M")
    link = settings.SITE_URL.rstrip("/") + reverse("alerta_detalhe", args=[alerta.pk])
    corpo = (
        f"{titulo}\n\n{alerta.mensagem}\n\n"
        f"Previsto: de {inicio} até {fim} (horário de São Paulo).\n"
        f"Falta(m) {formatar_duracao(alerta.janela_inicio - agora)} para o início previsto.\n\n"
        f"Veja o plano de prevenção da sua região: {link}\n\n{AVISO}\n"
    )
    return f"[AlertAção] {titulo}", corpo


def enviar_pendentes(agora=None):
    """Entrega aos provedores os e-mails PENDENTES. Retorna (enviados, falhas)."""
    pendentes = list(
        Notificacao.objects.filter(canal=CanalNotificacao.EMAIL, status=StatusEnvio.PENDENTE)
        .select_related("usuario", "alerta", "alerta__regiao")
    )
    enviados = falhas = 0
    if not pendentes:
        return enviados, falhas
    try:
        conexao = get_connection()
        conexao.open()
    except Exception:
        conexao = None
    for notificacao in pendentes:
        momento = agora or timezone.now()
        assunto, corpo = _montar_email(notificacao, momento)
        try:
            EmailMessage(assunto, corpo, to=[notificacao.usuario.email], connection=conexao).send()
        except Exception:
            notificacao.status = StatusEnvio.FALHA
            falhas += 1
        else:
            notificacao.status = StatusEnvio.ENVIADA
            notificacao.enviada_em = timezone.now()
            enviados += 1
        notificacao.save(update_fields=["status", "enviada_em"])
    if conexao is not None:
        try:
            conexao.close()
        except Exception:
            pass
    return enviados, falhas
