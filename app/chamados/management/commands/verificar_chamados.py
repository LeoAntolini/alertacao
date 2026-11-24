"""Rotina agendada dos chamados: marca SEM_RETORNO (RN09) e reenvia e-mails que falharam.

    python manage.py verificar_chamados
"""
from django.core.management.base import BaseCommand

from chamados.servicos import reenviar_abertos, verificar_sem_retorno


class Command(BaseCommand):
    help = "Marca chamados sem retorno e reenvia os que ficaram abertos."

    def handle(self, *args, **opcoes):
        sem_retorno = verificar_sem_retorno()
        enviados, falhas = reenviar_abertos()
        self.stdout.write(self.style.SUCCESS(
            f"Sem retorno: {sem_retorno}. E-mails reenviados: {enviados}. Falhas: {falhas}."
        ))
