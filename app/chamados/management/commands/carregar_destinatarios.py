"""Cria os destinatários de teste (caixas de e-mail controladas pelo grupo, nunca órgãos reais). Pode rodar de novo.

    python manage.py carregar_destinatarios --email grupo@exemplo.com
"""
from django.core.management.base import BaseCommand

from chamados.models import Destinatario, TipoDestinatario

PADRAO = [
    ("Subprefeitura (caixa de teste)", TipoDestinatario.SUBPREFEITURA, ["ARVORE", "DRENAGEM"]),
    ("Defesa Civil (caixa de teste)", TipoDestinatario.DEFESA_CIVIL, ["ENCOSTA"]),
    ("Concessionária de energia (caixa de teste)", TipoDestinatario.CONCESSIONARIA_ENERGIA, ["REDE_ELETRICA"]),
]


class Command(BaseCommand):
    help = "Cria os destinatários de teste do MVP."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Caixa de e-mail do grupo que receberá os chamados de teste")

    def handle(self, *args, **opcoes):
        for nome, tipo, categorias in PADRAO:
            Destinatario.objects.update_or_create(
                nome=nome, defaults={"tipo": tipo, "email": opcoes["email"], "categorias_atendidas": categorias}
            )
        self.stdout.write(self.style.SUCCESS(f"{len(PADRAO)} destinatários de teste prontos ({opcoes['email']})."))
