"""Entrega aos provedores os e-mails de notificação que ainda estão pendentes.

    python manage.py enviar_notificacoes
"""
from django.core.management.base import BaseCommand

from notificacoes.servicos import enviar_pendentes


class Command(BaseCommand):
    help = "Envia os e-mails de notificação pendentes."

    def handle(self, *args, **opcoes):
        enviados, falhas = enviar_pendentes()
        self.stdout.write(self.style.SUCCESS(f"E-mails enviados: {enviados}. Falhas: {falhas}."))
