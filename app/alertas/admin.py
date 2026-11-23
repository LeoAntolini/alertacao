from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from .models import Alerta, ModeloTarefa, Tarefa
from .servicos import publicar_alerta


@admin.action(description="Publicar alertas selecionados (gera o plano e notifica os moradores)")
def publicar(modeladmin, request, queryset):
    for alerta in queryset:
        try:
            resultado = publicar_alerta(alerta, request.user)
        except ValidationError as erro:
            modeladmin.message_user(request, f"{alerta}: {'; '.join(erro.messages)}", level=messages.ERROR)
        except PermissionDenied as erro:
            modeladmin.message_user(request, f"{alerta}: {erro}", level=messages.ERROR)
        else:
            modeladmin.message_user(
                request,
                (f"{alerta}: publicado para {resultado.moradores} moradores, com {resultado.tarefas} tarefas geradas; "
                 f"e-mails: {resultado.emails_enviados} enviados, {resultado.emails_com_falha} com falha."),
                level=messages.SUCCESS,
            )


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("__str__", "regiao", "evento", "nivel", "status", "janela_inicio", "publicado_em")
    list_filter = ("status", "evento", "nivel", "regiao")
    readonly_fields = ("origem", "status", "criado_em", "publicado_em", "publicado_por",
                       "encerrado_em", "ultimo_estagio_notificado")
    actions = [publicar]


@admin.register(ModeloTarefa)
class ModeloTarefaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "evento", "categoria", "ativo")
    list_filter = ("evento", "categoria", "ativo")
    search_fields = ("titulo", "instrucao")


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ("modelo", "usuario", "alerta", "status", "concluida_em")
    list_filter = ("status", "alerta")

    def has_add_permission(self, request):
        return False
