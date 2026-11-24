from django.contrib import admin

from .models import Chamado, Destinatario


@admin.register(Destinatario)
class DestinatarioAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "email", "categorias_atendidas")
    list_filter = ("tipo",)


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ("ponto", "destinatario", "status", "risco_iminente", "criado_em", "encaminhado_em")
    list_filter = ("status", "risco_iminente", "destinatario")
    readonly_fields = ("token_hash", "token_expira_em")

    def has_add_permission(self, request):
        return False
