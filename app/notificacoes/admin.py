from django.contrib import admin

from .models import Notificacao


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "canal", "estagio", "status", "alerta", "enviada_em")
    list_filter = ("canal", "status", "estagio")
    search_fields = ("usuario__email",)

    def has_add_permission(self, request):
        return False
