from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import PontoDeRisco


@admin.register(PontoDeRisco)
class PontoDeRiscoAdmin(GISModelAdmin):
    list_display = ("__str__", "categoria", "status", "regiao", "criado_em")
    list_filter = ("status", "categoria", "regiao")
    search_fields = ("descricao", "endereco")
