from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from .choices import StatusAlerta, StatusTarefa
from .models import Tarefa
from .servicos import encerrar_alertas, publicar_alerta
from .tests import Base


class EncerramentoTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.modelo("M1")
        self.modelo("M2", categoria=None)

    def vencido(self):
        """Alerta que começou há 5 h, durou 1 h (terminou há 4 h) e foi publicado há 6 h."""
        alerta = self.alerta(-5, duracao_h=1)
        publicar_alerta(alerta, self.resp, self.agora - timedelta(hours=6))
        return alerta

    def test_encerra_o_alerta_vencido_e_expira_so_as_tarefas_pendentes(self):
        alerta = self.vencido()
        pendente, concluida = Tarefa.objects.filter(usuario=self.ana).order_by("modelo__titulo")
        concluida.concluir(self.agora - timedelta(hours=5))
        self.assertEqual(encerrar_alertas(self.agora), (1, 1))
        alerta.refresh_from_db()
        pendente.refresh_from_db()
        concluida.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.ENCERRADO)
        self.assertEqual(alerta.encerrado_em, self.agora)
        self.assertEqual(pendente.status, StatusTarefa.EXPIRADA)
        self.assertEqual(pendente.expirada_em, self.agora)
        self.assertEqual(concluida.status, StatusTarefa.CONCLUIDA)

    def test_alerta_dentro_da_janela_nao_e_encerrado(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        self.assertEqual(encerrar_alertas(self.agora), (0, 0))
        alerta.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.PUBLICADO)

    def test_rascunho_vencido_nao_e_encerrado(self):
        rascunho = self.alerta(-5, duracao_h=1)
        self.assertEqual(encerrar_alertas(self.agora), (0, 0))
        rascunho.refresh_from_db()
        self.assertEqual(rascunho.status, StatusAlerta.RASCUNHO)

    def test_rodar_duas_vezes_nao_repete(self):
        self.vencido()
        self.assertEqual(encerrar_alertas(self.agora), (1, 2))
        self.assertEqual(encerrar_alertas(self.agora), (0, 0))

    def test_comando_encerrar_alertas(self):
        self.vencido()
        saida = StringIO()
        call_command("encerrar_alertas", stdout=saida)
        self.assertIn("Alertas encerrados: 1. Tarefas expiradas: 2.", saida.getvalue())

    def test_abrir_o_inicio_encerra_o_alerta_vencido_e_ele_some_da_lista(self):
        alerta = self.vencido()
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("inicio"))
        self.assertNotContains(resposta, reverse("alerta_detalhe", args=[alerta.pk]))
        alerta.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.ENCERRADO)
        self.assertEqual(Tarefa.objects.filter(status=StatusTarefa.EXPIRADA).count(), 2)

    def test_abrir_o_detalhe_de_alerta_vencido_encerra_e_da_404(self):
        alerta = self.vencido()
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("alerta_detalhe", args=[alerta.pk]))
        self.assertEqual(resposta.status_code, 404)
        alerta.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.ENCERRADO)
