from django.db import models


class Evento(models.TextChoices):
    CHUVA_FORTE = "CHUVA_FORTE", "Chuva forte"
    VENTANIA = "VENTANIA", "Ventania"


class CategoriaRisco(models.TextChoices):
    DRENAGEM = "DRENAGEM", "Drenagem (bueiros e alagamento)"
    ENCOSTA = "ENCOSTA", "Encosta (deslizamento)"
    ARVORE = "ARVORE", "Árvore"
    REDE_ELETRICA = "REDE_ELETRICA", "Rede elétrica (poste e fio)"


# RN06: nestas categorias o morador só relata e aciona o órgão; nunca recebe tarefa.
CATEGORIAS_SEM_TAREFA = (CategoriaRisco.ARVORE, CategoriaRisco.REDE_ELETRICA)


class NivelAlerta(models.TextChoices):
    BAIXO = "BAIXO", "Baixo"
    MODERADO = "MODERADO", "Moderado"
    ALTO = "ALTO", "Alto"


class OrigemAlerta(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    AUTOMATICA = "AUTOMATICA", "Automática"


class StatusAlerta(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    PUBLICADO = "PUBLICADO", "Publicado"
    ENCERRADO = "ENCERRADO", "Encerrado"
    CANCELADO = "CANCELADO", "Cancelado"


class EstagioAlerta(models.TextChoices):
    PREVISAO = "PREVISAO", "Previsão"
    PREPARACAO = "PREPARACAO", "Preparação"
    IMINENTE = "IMINENTE", "Iminente"


class StatusTarefa(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CONCLUIDA = "CONCLUIDA", "Concluída"
    DISPENSADA = "DISPENSADA", "Dispensada"
    ESCALADA = "ESCALADA", "Escalada"
    EXPIRADA = "EXPIRADA", "Expirada"
