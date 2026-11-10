from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Regiao


@admin.register(Regiao)
class RegiaoAdmin(GISModelAdmin):
    list_display = ("nome", "cidade")
    search_fields = ("nome",)
