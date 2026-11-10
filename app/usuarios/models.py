from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models


class Papel(models.TextChoices):
    MORADOR = "MORADOR", "Morador"
    RESPONSAVEL_SISTEMA = "RESPONSAVEL_SISTEMA", "Responsável pelo Sistema"


class Usuario(AbstractUser):
    """Usuário do AlertAção (classe Usuario do diagrama de classes).

    O login é feito com o e-mail: o campo username guarda sempre o mesmo valor do e-mail.
    criadoEm do diagrama corresponde a date_joined; senhaHash corresponde a password.
    """

    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField(max_length=150)
    papel = models.CharField(max_length=30, choices=Papel.choices, default=Papel.MORADOR)
    regiao = models.ForeignKey(
        "regioes.Regiao", null=True, blank=True, on_delete=models.PROTECT, related_name="moradores"
    )
    # Localizacao (objeto de valor) embutida: ponto, endereço e precisão
    ponto_referencia = models.PointField(srid=4326, null=True, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    precisao_metros = models.FloatField(null=True, blank=True)
    consentimento_em = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = ["email", "nome"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.username = self.email
        if self.is_superuser:
            self.papel = Papel.RESPONSAVEL_SISTEMA
        super().save(*args, **kwargs)
