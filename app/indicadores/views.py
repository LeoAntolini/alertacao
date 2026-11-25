import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from alertas.choices import CategoriaRisco
from usuarios.models import Papel

from .servicos import calcular

logger = logging.getLogger("alertacao.seguranca")
PERIODOS = (7, 30, 90)

DEFINICOES = [
    ("i1", "I1", "Antecedência média dos alertas", "h", "Média de (início previsto − publicação) dos alertas publicados no período."),
    ("i2", "I2", "Adesão ao plano de prevenção", "%", "Tarefas concluídas ÷ (tarefas geradas − dispensadas)."),
    ("i3", "I3", "Pontos tratados antes do evento", "%", "Pontos ativos na publicação que ficaram resolvidos até o início previsto ÷ pontos ativos na publicação."),
    ("i4", "I4", "Tempo médio de resolução de chamados", "h", "Média de (resolução − encaminhamento) dos chamados resolvidos."),
    ("i5", "I5", "Retorno do destinatário", "%", "Chamados com ação do órgão ÷ chamados encaminhados."),
    ("i6", "I6", "Cobertura de notificação", "%", "Moradores notificados ÷ moradores ativos da região, por alerta (moradores contados hoje)."),
    ("i8", "I8", "Tempo até concluir a tarefa", "h", "Média de (conclusão da tarefa − publicação do alerta)."),
]


@login_required
def painel(request):
    """RF08: painel de indicadores, só para o Responsável pelo Sistema (RNF06)."""
    if request.user.papel != Papel.RESPONSAVEL_SISTEMA:
        logger.warning("Acesso negado ao painel de indicadores: usuário %s", request.user.pk)
        raise PermissionDenied
    try:
        dias = int(request.GET.get("dias", 30))
    except ValueError:
        dias = 30
    if dias not in PERIODOS:
        dias = 30
    dados = calcular(dias)
    linhas = [
        {"codigo": cod, "nome": nome, "valor": dados[chave], "unidade": unidade, "formula": formula}
        for chave, cod, nome, unidade, formula in DEFINICOES
    ]
    rotulos = dict(CategoriaRisco.choices)
    concentracao = [
        {"regiao": i["regiao"], "categoria": rotulos.get(i["categoria"], i["categoria"]), "n": i["n"]} for i in dados["i7"]
    ]
    contexto = {"dados": dados, "linhas": linhas, "concentracao": concentracao, "periodos": PERIODOS}
    return render(request, "indicadores/painel.html", contexto)
