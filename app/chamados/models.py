import hashlib
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models

PRAZO_LINK = timedelta(days=30)           # RN08
PRAZO_SEM_RETORNO = timedelta(hours=72)   # RN09


class TipoDestinatario(models.TextChoices):
    DEFESA_CIVIL = "DEFESA_CIVIL", "Defesa Civil"
    SUBPREFEITURA = "SUBPREFEITURA", "Subprefeitura"
    CONCESSIONARIA_ENERGIA = "CONCESSIONARIA_ENERGIA", "Concessionária de energia"


class StatusChamado(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    ENCAMINHADO = "ENCAMINHADO", "Encaminhado ao órgão"
    EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em atendimento"
    RESOLVIDO = "RESOLVIDO", "Resolvido"
    SEM_RETORNO = "SEM_RETORNO", "Sem retorno do órgão"
    NAO_PROCEDE = "NAO_PROCEDE", "Não procede"


STATUS_FINAIS = (StatusChamado.RESOLVIDO, StatusChamado.NAO_PROCEDE)


class ResolvidoPor(models.TextChoices):
    DESTINATARIO = "DESTINATARIO", "Órgão"
    MORADOR = "MORADOR", "Morador"


class Destinatario(models.Model):
    """Órgão externo que recebe chamados por e-mail, sem login (D04)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=150, unique=True)
    tipo = models.CharField(max_length=30, choices=TipoDestinatario.choices)
    email = models.EmailField()
    categorias_atendidas = models.JSONField(default=list, help_text="Lista de categorias, por exemplo: [\"ARVORE\", \"DRENAGEM\"]")

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def atende(self, categoria):
        return categoria in self.categorias_atendidas


class Chamado(models.Model):
    """Pedido de ajuda ao órgão responsável, vinculado a um ponto de risco (classe Chamado)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="chamados"
    )
    ponto = models.ForeignKey("pontos.PontoDeRisco", on_delete=models.PROTECT, related_name="chamados")
    tarefa = models.OneToOneField(
        "alertas.Tarefa", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamado"
    )
    destinatario = models.ForeignKey(Destinatario, on_delete=models.PROTECT, related_name="chamados")
    descricao = models.TextField()
    risco_iminente = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=StatusChamado.choices, default=StatusChamado.ABERTO)
    token_hash = models.CharField(max_length=64, unique=True)
    token_expira_em = models.DateTimeField()
    criado_em = models.DateTimeField(auto_now_add=True)
    encaminhado_em = models.DateTimeField(null=True, blank=True)
    em_atendimento_em = models.DateTimeField(null=True, blank=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.CharField(max_length=12, choices=ResolvidoPor.choices, null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.ponto} ({self.get_status_display()})"

    @property
    def finalizado(self):
        return self.status in STATUS_FINAIS

    @staticmethod
    def hash_do_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
