from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "nome", "papel", "regiao", "is_staff")
    list_filter = ("papel", "regiao", "is_staff")
    search_fields = ("email", "nome")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados", {"fields": ("nome", "papel", "regiao", "endereco", "ponto_referencia",
                              "precisao_metros", "consentimento_em")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nome", "papel", "password1", "password2")}),
    )
