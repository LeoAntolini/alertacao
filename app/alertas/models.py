import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .choices import (
    CATEGORIAS_SEM_TAREFA,
    CategoriaRisco,
    EstagioAlerta,
    Evento,
    NivelAlerta,
    OrigemAlerta,
    StatusAlerta,
    StatusTarefa,
)

HORIZONTE_MAXIMO = timedelta(days=7)  # D07


class Alerta(models.Model):
    """Aviso de uma região para um evento, com janela prevista (classe Alerta do diagrama)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regiao = models.ForeignKey("regioes.Regiao", on_delete=models.PROTECT, related_name="alertas")
    evento = models.CharField(max_length=20, choices=Evento.choices)
    nivel = models.CharField(max_length=10, choices=NivelAlerta.choices)
    origem = models.CharField(max_length=12, choices=OrigemAlerta.choices, default=OrigemAlerta.MANUAL)
    fonte = models.CharField(max_length=100, blank=True)
    janela_inicio = models.DateTimeField("início previsto")
    janela_fim = models.DateTimeField("fim previsto")
    mensagem = models.TextField()
    status = models.CharField(max_length=10, choices=StatusAlerta.choices, default=StatusAlerta.RASCUNHO)
    criado_em = models.DateTimeField(auto_now_add=True)
    publicado_em = models.DateTimeField(null=True, blank=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)
    ultimo_estagio_notificado = models.CharField(
        max_length=12, choices=EstagioAlerta.choices, null=True, blank=True
    )
    publicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="alertas_publicados",
    )

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.get_evento_display()} em {self.regiao.nome} ({self.janela_inicio:%d/%m %H:%M})"

    def antecedencia(self, agora=None):
        """Início previsto menos o instante de publicação (ou menos 'agora', se ainda não foi publicado)."""
        referencia = agora or self.publicado_em or timezone.now()
        return self.janela_inicio - referencia

    def estagio(self, agora=None):
        """Estágio derivado da antecedência (D07): PREVISÃO > 72 h, PREPARAÇÃO de 24 a 72 h, IMINENTE < 24 h."""
        horas = (self.janela_inicio - (agora or timezone.now())).total_seconds() / 3600
        if horas > 72:
            return EstagioAlerta.PREVISAO
        if horas >= 24:
            return EstagioAlerta.PREPARACAO
        return EstagioAlerta.IMINENTE

    def validar_janela(self, agora):
        """Regras da janela prevista (RF04)."""
        if self.janela_fim <= self.janela_inicio:
            raise ValidationError("O fim da janela deve ser depois do início.")
        if self.janela_inicio < agora:
            raise ValidationError("O início da janela não pode ser anterior à hora atual.")
        if self.janela_inicio > agora + HORIZONTE_MAXIMO:
            raise ValidationError("O início da janela não pode passar de 7 dias.")


class ModeloTarefa(models.Model):
    """Texto-base de uma ação preventiva (classe ModeloTarefa). Sem categoria = vale para todo o evento."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evento = models.CharField(max_length=20, choices=Evento.choices)
    categoria = models.CharField(max_length=20, choices=CategoriaRisco.choices, null=True, blank=True)
    titulo = models.CharField(max_length=200)
    instrucao = models.TextField()
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["evento", "titulo"]
        constraints = [
            models.UniqueConstraint(fields=["evento", "titulo"], name="modelo_tarefa_unico_por_evento_e_titulo"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.get_evento_display()})"

    def clean(self):
        if self.categoria in CATEGORIAS_SEM_TAREFA:
            raise ValidationError({"categoria": "Árvore e rede elétrica não têm tarefa: o morador só relata e aciona o órgão (RN06)."})


class Tarefa(models.Model):
    """Instância individual de um modelo de tarefa para um morador (classe Tarefa)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alerta = models.ForeignKey(Alerta, on_delete=models.CASCADE, related_name="tarefas")
    modelo = models.ForeignKey(ModeloTarefa, on_delete=models.PROTECT, related_name="tarefas")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tarefas")
    status = models.CharField(max_length=10, choices=StatusTarefa.choices, default=StatusTarefa.PENDENTE)
    criada_em = models.DateTimeField(auto_now_add=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    dispensada_em = models.DateTimeField(null=True, blank=True)
    escalada_em = models.DateTimeField(null=True, blank=True)
    expirada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["criada_em"]
        constraints = [
            models.UniqueConstraint(fields=["alerta", "modelo", "usuario"], name="tarefa_unica_por_alerta_modelo_e_usuario"),
        ]

    def __str__(self):
        return f"{self.modelo.titulo} - {self.usuario.email}"

    def _mudar(self, novo_status, campo, agora):
        if self.status != StatusTarefa.PENDENTE:
            raise ValidationError("Só tarefas pendentes podem mudar de estado.")
        self.status = novo_status
        setattr(self, campo, agora or timezone.now())
        self.save(update_fields=["status", campo])

    def concluir(self, agora=None):
        """RF06: registra estado e carimbo de tempo; a ação não é reversível (RN05)."""
        self._mudar(StatusTarefa.CONCLUIDA, "concluida_em", agora)

    def dispensar(self, agora=None):
        """RF16: 'Não se aplica'."""
        self._mudar(StatusTarefa.DISPENSADA, "dispensada_em", agora)

    def expirar(self, agora=None):
        """RN04: o alerta acabou e a tarefa não foi feita."""
        self._mudar(StatusTarefa.EXPIRADA, "expirada_em", agora)
