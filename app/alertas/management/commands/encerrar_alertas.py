"""Encerra os alertas vencidos e expira as tarefas pendentes deles (RF21).

    python manage.py encerrar_alertas
"""
from django.core.management.base import BaseCommand

from alertas.servicos import encerrar_alertas


class Command(BaseCommand):
    help = "Encerra os alertas cujo fim da janela já passou."

    def handle(self, *args, **opcoes):
        alertas, tarefas = encerrar_alertas()
        self.stdout.write(self.style.SUCCESS(f"Alertas encerrados: {alertas}. Tarefas expiradas: {tarefas}."))
