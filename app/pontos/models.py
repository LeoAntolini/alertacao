import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.utils import timezone

from alertas.choices import CategoriaRisco


class StatusPonto(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    RESOLVIDO = "RESOLVIDO", "Resolvido"


class PontoDeRisco(models.Model):
    """Risco relatado por um morador, com localização (classe PontoDeRisco do diagrama).

    A autoria não é exibida a outros moradores (RN10, RNF09).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pontos_relatados"
    )
    regiao = models.ForeignKey("regioes.Regiao", on_delete=models.PROTECT, related_name="pontos")
    categoria = models.CharField(max_length=20, choices=CategoriaRisco.choices)
    descricao = models.TextField(validators=[MaxLengthValidator(500)])
    # Localizacao (objeto de valor) embutida: ponto, endereço de referência e precisão
    localizacao = models.PointField(srid=4326)
    endereco = models.CharField(max_length=255, blank=True)
    precisao_metros = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=StatusPonto.choices, default=StatusPonto.ATIVO)
    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "ponto de risco"
        verbose_name_plural = "pontos de risco"

    def __str__(self):
        return f"{self.get_categoria_display()} em {self.regiao.nome}"

    def resolver(self, agora=None):
        """Marca o ponto como resolvido (usado pela confirmação do chamado, RF20)."""
        if self.status != StatusPonto.ATIVO:
            raise ValidationError("Só pontos ativos podem ser resolvidos.")
        self.status = StatusPonto.RESOLVIDO
        self.resolvido_em = agora or timezone.now()
        self.save(update_fields=["status", "resolvido_em"])
