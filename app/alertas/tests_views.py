from datetime import timedelta

from django.urls import reverse

from .choices import StatusTarefa
from .models import Tarefa
from .servicos import publicar_alerta
from .tests import Base
from .utils import formatar_duracao


class DuracaoTests(Base):
    def test_formata_duracoes(self):
        casos = [
            (timedelta(days=2, hours=3), "2 dias e 3 horas"),
            (timedelta(days=1), "1 dia"),
            (timedelta(hours=5, minutes=10), "5 horas e 10 minutos"),
            (timedelta(minutes=20), "20 minutos"),
            (timedelta(seconds=30), "menos de 1 minuto"),
            (timedelta(seconds=-5), "agora"),
        ]
        for delta, esperado in casos:
            with self.subTest(delta=delta):
                self.assertEqual(formatar_duracao(delta), esperado)


class TelasDoMoradorTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.modelo("Limpar grade")
        self.modelo("Guardar objetos", categoria=None)
        self.alerta_pub = self.alerta(48)
        publicar_alerta(self.alerta_pub, self.resp, self.agora)
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        self.url = reverse("alerta_detalhe", args=[self.alerta_pub.pk])

    def _tarefa(self, titulo):
        return Tarefa.objects.get(usuario=self.ana, modelo__titulo=titulo)

    def test_inicio_lista_o_alerta_ativo_da_regiao(self):
        de_outra_regiao = self.alerta(30, regiao=self.outra)
        publicar_alerta(de_outra_regiao, self.resp, self.agora)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, self.url)
        self.assertNotContains(resposta, reverse("alerta_detalhe", args=[de_outra_regiao.pk]))

    def test_detalhe_mostra_os_elementos_do_alerta_e_o_plano(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        for trecho in ("Chuva forte", "R1", "Nível Moderado", "Preparação", "Antecedência restante",
                       "Manual", "Não substitui alertas oficiais", "199", "193",
                       "Limpar grade", "Guardar objetos", "0 de 2"):
            self.assertContains(resposta, trecho)

    def test_detalhe_exige_login(self):
        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta["Location"])

    def test_alerta_de_outra_regiao_nao_aparece(self):
        outro = self.alerta(30, regiao=self.outra)
        publicar_alerta(outro, self.resp, self.agora)
        resposta = self.client.get(reverse("alerta_detalhe", args=[outro.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_rascunho_nao_aparece_para_o_morador(self):
        rascunho = self.alerta(30)
        resposta = self.client.get(reverse("alerta_detalhe", args=[rascunho.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_concluir_tarefa_registra_e_atualiza_o_progresso(self):
        tarefa = self._tarefa("Limpar grade")
        resposta = self.client.post(reverse("tarefa_concluir", args=[tarefa.pk]), follow=True)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.CONCLUIDA)
        self.assertIsNotNone(tarefa.concluida_em)
        self.assertContains(resposta, "1 de 2")
        self.assertContains(resposta, "Tarefa concluída.")

    def test_concluir_duas_vezes_mostra_erro_e_nao_muda(self):
        tarefa = self._tarefa("Limpar grade")
        url = reverse("tarefa_concluir", args=[tarefa.pk])
        self.client.post(url)
        resposta = self.client.post(url, follow=True)
        self.assertContains(resposta, "Só tarefas pendentes")
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.CONCLUIDA)

    def test_dispensar_tira_a_tarefa_do_denominador(self):
        tarefa = self._tarefa("Guardar objetos")
        resposta = self.client.post(reverse("tarefa_dispensar", args=[tarefa.pk]), follow=True)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.DISPENSADA)
        self.assertContains(resposta, "0 de 1")

    def test_so_o_dono_mexe_na_tarefa(self):
        self.morador("bia@x.com")
        # a Bia recebe tarefas só de alertas publicados depois que ela existe
        outro = self.alerta(36)
        publicar_alerta(outro, self.resp, self.agora)
        tarefa_da_bia = Tarefa.objects.filter(alerta=outro, usuario__email="bia@x.com").first()
        resposta = self.client.post(reverse("tarefa_concluir", args=[tarefa_da_bia.pk]))
        self.assertEqual(resposta.status_code, 404)
        tarefa_da_bia.refresh_from_db()
        self.assertEqual(tarefa_da_bia.status, StatusTarefa.PENDENTE)

    def test_concluir_so_aceita_post(self):
        tarefa = self._tarefa("Limpar grade")
        resposta = self.client.get(reverse("tarefa_concluir", args=[tarefa.pk]))
        self.assertEqual(resposta.status_code, 405)
