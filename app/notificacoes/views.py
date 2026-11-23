from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import CanalNotificacao, Notificacao


@login_required
def lista(request):
    """Caixa de entrada do morador (RF14)."""
    itens = (
        Notificacao.objects.filter(usuario=request.user, canal=CanalNotificacao.APP)
        .select_related("alerta", "alerta__regiao")
        .order_by("-enviada_em")
    )
    return render(request, "notificacoes/lista.html", {"itens": itens})
