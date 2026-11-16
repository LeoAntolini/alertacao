"""Carrega o catálogo inicial de modelos de tarefa (MT01 a MT10). Pode rodar mais de uma vez.

    python manage.py carregar_modelos_tarefa
"""
from django.core.management.base import BaseCommand

from alertas.catalogo import CATALOGO
from alertas.models import ModeloTarefa


class Command(BaseCommand):
    help = "Carrega o catálogo inicial de modelos de tarefa (seção 6.1 do Documento-Base)."

    def handle(self, *args, **opcoes):
        criados = atualizados = 0
        for codigo, evento, categoria, titulo, instrucao in CATALOGO:
            _, criado = ModeloTarefa.objects.update_or_create(
                evento=evento,
                titulo=titulo,
                defaults={"categoria": categoria, "instrucao": instrucao},
            )
            if criado:
                criados += 1
            else:
                atualizados += 1
        self.stdout.write(self.style.SUCCESS(f"Catálogo carregado: {criados} criados, {atualizados} atualizados."))
