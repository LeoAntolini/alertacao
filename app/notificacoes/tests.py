from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from alertas.choices import EstagioAlerta
from alertas.servicos import publicar_alerta
from alertas.tests import Base
from usuarios.models import Papel, Usuario

from .models import CanalNotificacao, Notificacao, StatusEnvio
from .servicos import enviar_pendentes, notificar_alerta


class BackendQueFalha(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise OSError("provedor indisponível")


class NotificarTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.bia = self.morador("bia@x.com")
        self.morador("fora@x.com", regiao=self.outra)
        self.morador("inativo@x.com", ativo=False)
        self.modelo("M1")

    def test_publicar_notifica_so_os_moradores_ativos_da_regiao_por_app_e_email(self):
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual(Notificacao.objects.count(), 4)
        self.assertEqual(
            set(Notificacao.objects.values_list("usuario__email", flat=True)), {"ana@x.com", "bia@x.com"}
        )
        self.assertEqual(Notificacao.objects.filter(canal=CanalNotificacao.APP).count(), 2)
        self.assertEqual(Notificacao.objects.filter(canal=CanalNotificacao.EMAIL).count(), 2)

    def test_app_fica_entregue_e_email_fica_enviado(self):
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        for n in Notificacao.objects.filter(canal=CanalNotificacao.APP):
            self.assertEqual(n.status, StatusEnvio.ENTREGUE)
        for n in Notificacao.objects.filter(canal=CanalNotificacao.EMAIL):
            self.assertEqual(n.status, StatusEnvio.ENVIADA)
            self.assertIsNotNone(n.enviada_em)

    def test_email_tem_assunto_corpo_link_e_aviso(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        self.assertEqual(len(mail.outbox), 2)
        email = mail.outbox[0]
        self.assertIn("Hora de se preparar", email.subject)
        self.assertIn("chuva forte em R1", email.subject)
        self.assertIn(reverse("alerta_detalhe", args=[alerta.pk]), email.body)
        self.assertIn("Não substitui alertas oficiais", email.body)
        self.assertIn("199", email.body)
        self.assertIn("193", email.body)

    def test_titulo_muda_com_o_estagio(self):
        publicar_alerta(self.alerta(120), self.resp, self.agora)
        publicar_alerta(self.alerta(12, evento="VENTANIA"), self.resp, self.agora)
        assuntos = " | ".join(m.subject for m in mail.outbox)
        self.assertIn("Previsão", assuntos)
        self.assertIn("Atenção, evento iminente", assuntos)

    def test_notificar_de_novo_no_mesmo_estagio_nao_duplica(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        notificar_alerta(alerta, [self.ana, self.bia], self.agora)
        self.assertEqual(Notificacao.objects.count(), 4)

    def test_mudanca_de_estagio_gera_nova_notificacao(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        notificar_alerta(alerta, [self.ana], self.agora, estagio=EstagioAlerta.IMINENTE)
        self.assertEqual(Notificacao.objects.filter(usuario=self.ana, canal=CanalNotificacao.APP).count(), 2)

    @override_settings(EMAIL_BACKEND="notificacoes.tests.BackendQueFalha")
    def test_falha_no_provedor_marca_falha_e_nao_derruba_a_publicacao(self):
        alerta = self.alerta(48)
        resultado = publicar_alerta(alerta, self.resp, self.agora)
        self.assertEqual(resultado.moradores, 2)
        self.assertEqual(Notificacao.objects.filter(status=StatusEnvio.FALHA).count(), 2)
        self.assertEqual(Notificacao.objects.filter(canal=CanalNotificacao.APP, status=StatusEnvio.ENTREGUE).count(), 2)

    def test_comando_envia_os_pendentes(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        Notificacao.objects.filter(canal=CanalNotificacao.EMAIL).update(status=StatusEnvio.PENDENTE)
        mail.outbox.clear()
        saida = StringIO()
        call_command("enviar_notificacoes", stdout=saida)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("E-mails enviados: 2", saida.getvalue())
        self.assertEqual(enviar_pendentes(), (0, 0))


class DesempenhoTests(Base):
    def test_500_moradores_todos_notificados_e_entregues_aos_provedores_em_ate_60_s(self):
        self.modelo("M1")
        Usuario.objects.bulk_create([
            Usuario(username=f"u{i}@x.com", email=f"u{i}@x.com", nome=f"U{i}", papel=Papel.MORADOR, regiao=self.regiao)
            for i in range(500)
        ])
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        alerta.refresh_from_db()
        self.assertEqual(Notificacao.objects.filter(canal=CanalNotificacao.APP).count(), 500)
        emails = Notificacao.objects.filter(canal=CanalNotificacao.EMAIL)
        self.assertEqual(emails.count(), 500)
        for n in emails:
            self.assertEqual(n.status, StatusEnvio.ENVIADA)
            self.assertLessEqual((n.enviada_em - alerta.publicado_em).total_seconds(), 60)
        self.assertEqual(len(mail.outbox), 500)


class CaixaDeEntradaTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.bia = self.morador("bia@x.com")
        self.modelo("M1")
        self.alerta_pub = self.alerta(48)
        publicar_alerta(self.alerta_pub, self.resp, self.agora)

    def test_morador_ve_a_propria_notificacao_com_link(self):
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("notificacoes"))
        self.assertContains(resposta, "Hora de se preparar")
        self.assertContains(resposta, reverse("alerta_detalhe", args=[self.alerta_pub.pk]))

    def test_so_aparecem_notificacoes_do_proprio_morador(self):
        self.morador("carla@x.com", regiao=self.outra)
        self.client.login(username="carla@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("notificacoes"))
        self.assertContains(resposta, "Você ainda não recebeu notificações.")

    def test_exige_login(self):
        resposta = self.client.get(reverse("notificacoes"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta["Location"])
