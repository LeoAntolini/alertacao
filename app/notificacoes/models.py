import uuid

from django.conf import settings
from django.db import models

from alertas.choices import EstagioAlerta


class CanalNotificacao(models.TextChoices):
    APP = "APP", "Caixa de entrada"
    EMAIL = "EMAIL", "E-mail"
    PUSH = "PUSH", "Web push"


class StatusEnvio(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    ENVIADA = "ENVIADA", "Enviada ao provedor"
    ENTREGUE = "ENTREGUE", "Entregue"
    FALHA = "FALHA", "Falha"


PREFIXO_POR_ESTAGIO = {
    EstagioAlerta.PREVISAO: "Previsão",
    EstagioAlerta.PREPARACAO: "Hora de se preparar",
    EstagioAlerta.IMINENTE: "Atenção, evento iminente",
}


def titulo_notificacao(alerta, estagio):
    return (
        f"{PREFIXO_POR_ESTAGIO[estagio]}: {alerta.get_evento_display().lower()} em "
        f"{alerta.regiao.nome} (nível {alerta.get_nivel_display().lower()})"
    )


class Notificacao(models.Model):
    """Aviso de um alerta para um morador por um canal (classe Notificacao).

    APP: fica ENTREGUE assim que é registrada na caixa de entrada.
    EMAIL: PENDENTE até ser entregue ao provedor de e-mail (ENVIADA) ou FALHA.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alerta = models.ForeignKey("alertas.Alerta", on_delete=models.CASCADE, related_name="notificacoes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificacoes")
    canal = models.CharField(max_length=6, choices=CanalNotificacao.choices)
    estagio = models.CharField(max_length=12, choices=EstagioAlerta.choices)
    status = models.CharField(max_length=10, choices=StatusEnvio.choices, default=StatusEnvio.PENDENTE)
    criada_em = models.DateTimeField(auto_now_add=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    entregue_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["alerta", "usuario", "canal", "estagio"],
                name="notificacao_unica_por_alerta_usuario_canal_e_estagio",
            ),
        ]

    def __str__(self):
        return f"{self.get_canal_display()} para {self.usuario.email}"

    def titulo(self):
        return titulo_notificacao(self.alerta, self.estagio)
