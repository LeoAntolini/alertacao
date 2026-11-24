from datetime import timedelta
from io import StringIO

from django.contrib.gis.geos import Point
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail.backends.base import BaseEmailBackend
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from alertas.choices import CategoriaRisco, StatusTarefa
from alertas.models import Tarefa
from alertas.servicos import publicar_alerta
from alertas.tests import Base
from pontos.models import PontoDeRisco, StatusPonto

from .models import Chamado, Destinatario, ResolvidoPor, StatusChamado, TipoDestinatario
from .servicos import (
    abrir_chamado, chamado_do_token, encaminhar, registrar_acao, reenviar_abertos, rotear, verificar_sem_retorno,
)

DENTRO = {"latitude": "-23.72", "longitude": "-46.78"}   # dentro de R1
FORA = {"latitude": "-23.55", "longitude": "-46.63"}     # dentro de R2


class BackendQueFalha(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise OSError("provedor indisponível")


class BaseChamados(Base):
    def setUp(self):
        super().setUp()
        Destinatario.objects.create(nome="Subprefeitura", tipo=TipoDestinatario.SUBPREFEITURA,
                                    email="sub@teste.local", categorias_atendidas=["ARVORE", "DRENAGEM"])
        Destinatario.objects.create(nome="Defesa Civil", tipo=TipoDestinatario.DEFESA_CIVIL,
                                    email="dc@teste.local", categorias_atendidas=["ENCOSTA"])
        Destinatario.objects.create(nome="Concessionária", tipo=TipoDestinatario.CONCESSIONARIA_ENERGIA,
                                    email="enel@teste.local", categorias_atendidas=["REDE_ELETRICA"])
        self.ana = self.morador("ana@x.com")

    def ponto(self, categoria=CategoriaRisco.ARVORE, regiao=None, autor=None, descricao="Árvore inclinada sobre a casa"):
        return PontoDeRisco.objects.create(
            autor=autor or self.ana, regiao=regiao or self.regiao, categoria=categoria, descricao=descricao,
            endereco="Rua Exemplo, 100", localizacao=Point(-46.78, -23.72, srid=4326),
        )

    def chamado(self, ponto=None, risco=False, **kw):
        chamado, enviado = abrir_chamado(self.ana, ponto or self.ponto(), "Preciso de ajuda", risco, **kw)
        return chamado


class AbrirChamadoTests(BaseChamados):
    def test_roteia_pela_categoria(self):
        casos = {"ARVORE": "sub@teste.local", "DRENAGEM": "sub@teste.local",
                 "ENCOSTA": "dc@teste.local", "REDE_ELETRICA": "enel@teste.local"}
        for categoria, email in casos.items():
            with self.subTest(categoria=categoria):
                self.assertEqual(rotear(categoria).email, email)

    def test_cria_chamado_encaminha_por_email_e_registra_a_data(self):
        chamado, enviado = abrir_chamado(self.ana, self.ponto(), "Árvore vai cair", True)
        chamado.refresh_from_db()
        self.assertTrue(enviado)
        self.assertEqual(chamado.status, StatusChamado.ENCAMINHADO)
        self.assertIsNotNone(chamado.encaminhado_em)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["sub@teste.local"])

    def test_email_traz_dados_do_chamado_sem_expor_o_autor(self):
        self.chamado(self.ponto(CategoriaRisco.REDE_ELETRICA), risco=True)
        email = mail.outbox[0]
        self.assertIn("URGENTE", email.subject)
        for trecho in ("Risco iminente: SIM", "Árvore inclinada sobre a casa", "Rua Exemplo, 100",
                       "-23.720000", "-46.780000", "openstreetmap.org", "/chamados/acao/",
                       "não substitui o registro oficial", "sp156.prefeitura.sp.gov.br"):
            self.assertIn(trecho, email.body)
        self.assertNotIn("ana@x.com", email.body)
        self.assertEqual(email.to, ["enel@teste.local"])

    def test_token_e_guardado_so_como_hash(self):
        chamado = self.chamado()
        token = mail.outbox[0].body.split("/chamados/acao/")[1].split("/")[0]
        chamado.refresh_from_db()
        self.assertNotEqual(chamado.token_hash, token)
        self.assertEqual(chamado.token_hash, Chamado.hash_do_token(token))
        self.assertEqual(chamado_do_token(token), chamado)

    def test_sem_destinatario_para_a_categoria_recusa_e_nao_cria_nada(self):
        Destinatario.objects.filter(nome="Defesa Civil").delete()
        with self.assertRaises(ValidationError):
            abrir_chamado(self.ana, self.ponto(CategoriaRisco.ENCOSTA), "x")
        self.assertEqual(Chamado.objects.count(), 0)

    def test_ponto_de_outra_regiao_e_recusado(self):
        with self.assertRaises(PermissionDenied):
            abrir_chamado(self.ana, self.ponto(regiao=self.outra), "x")

    def test_ponto_resolvido_nao_recebe_chamado(self):
        ponto = self.ponto()
        ponto.resolver(self.agora)
        with self.assertRaises(ValidationError):
            abrir_chamado(self.ana, ponto, "x")

    def test_nao_abre_segundo_chamado_em_andamento_mas_abre_depois_de_nao_procede(self):
        ponto = self.ponto()
        primeiro = self.chamado(ponto)
        with self.assertRaises(ValidationError):
            abrir_chamado(self.ana, ponto, "de novo")
        registrar_acao(primeiro, "NAO_PROCEDE")
        segundo, _ = abrir_chamado(self.ana, ponto, "de novo")
        self.assertEqual(Chamado.objects.filter(ponto=ponto).count(), 2)
        self.assertEqual(segundo.status, StatusChamado.ENCAMINHADO)

    def test_tarefa_de_origem_fica_escalada(self):
        self.modelo("M1")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        tarefa = Tarefa.objects.get(usuario=self.ana)
        chamado = self.chamado(tarefa=tarefa)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.ESCALADA)
        self.assertIsNotNone(tarefa.escalada_em)
        self.assertEqual(chamado.tarefa, tarefa)

    def test_tarefa_de_outro_morador_e_recusada(self):
        self.modelo("M1")
        bia = self.morador("bia@x.com")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        tarefa_da_bia = Tarefa.objects.get(usuario=bia)
        with self.assertRaises(PermissionDenied):
            abrir_chamado(self.ana, self.ponto(), "x", tarefa=tarefa_da_bia)

    @override_settings(EMAIL_BACKEND="chamados.tests.BackendQueFalha")
    def test_falha_de_email_deixa_o_chamado_aberto_e_o_reenvio_funciona(self):
        chamado, enviado = abrir_chamado(self.ana, self.ponto(), "x")
        self.assertFalse(enviado)
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, StatusChamado.ABERTO)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.assertEqual(reenviar_abertos(), (1, 0))
        chamado.refresh_from_db()
        self.assertEqual(chamado.status, StatusChamado.ENCAMINHADO)


class LinkDoDestinatarioTests(BaseChamados):
    def setUp(self):
        super().setUp()
        self.ponto_obj = self.ponto()
        self.chamado_obj = self.chamado(self.ponto_obj, risco=True)
        self.token = mail.outbox[0].body.split("/chamados/acao/")[1].split("/")[0]
        self.url = reverse("chamado_acao", args=[self.token])

    def test_pagina_abre_sem_login_e_mostra_os_dados_sem_autoria(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        for trecho in ("Árvore", "R1", "SIM", "Preciso de ajuda", "Em atendimento", "Resolvido", "Não procede"):
            self.assertContains(resposta, trecho)
        self.assertNotContains(resposta, "ana@x.com")

    def test_em_atendimento_registra_estado_e_data(self):
        self.client.post(self.url, {"acao": "EM_ATENDIMENTO"})
        self.chamado_obj.refresh_from_db()
        self.assertEqual(self.chamado_obj.status, StatusChamado.EM_ATENDIMENTO)
        self.assertIsNotNone(self.chamado_obj.em_atendimento_em)

    def test_resolvido_resolve_o_ponto_e_o_link_deixa_de_valer(self):
        self.client.post(self.url, {"acao": "RESOLVIDO"})
        self.chamado_obj.refresh_from_db()
        self.ponto_obj.refresh_from_db()
        self.assertEqual(self.chamado_obj.status, StatusChamado.RESOLVIDO)
        self.assertEqual(self.chamado_obj.resolvido_por, ResolvidoPor.DESTINATARIO)
        self.assertEqual(self.ponto_obj.status, StatusPonto.RESOLVIDO)
        self.assertEqual(self.client.get(self.url).status_code, 410)

    def test_nao_procede_encerra_o_chamado_e_mantem_o_ponto_ativo(self):
        self.client.post(self.url, {"acao": "NAO_PROCEDE"})
        self.chamado_obj.refresh_from_db()
        self.ponto_obj.refresh_from_db()
        self.assertEqual(self.chamado_obj.status, StatusChamado.NAO_PROCEDE)
        self.assertEqual(self.ponto_obj.status, StatusPonto.ATIVO)
        self.assertEqual(self.client.get(self.url).status_code, 410)

    def test_link_invalido_e_expirado_dao_410(self):
        self.assertEqual(self.client.get(reverse("chamado_acao", args=["token-que-nao-existe"])).status_code, 410)
        Chamado.objects.update(token_expira_em=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(self.url).status_code, 410)

    def test_acao_desconhecida_da_400(self):
        resposta = self.client.post(self.url, {"acao": "APAGAR"})
        self.assertEqual(resposta.status_code, 400)

    def test_resposta_tardia_depois_de_sem_retorno_e_aceita(self):
        Chamado.objects.update(status=StatusChamado.SEM_RETORNO)
        self.client.post(self.url, {"acao": "RESOLVIDO"})
        self.chamado_obj.refresh_from_db()
        self.assertEqual(self.chamado_obj.status, StatusChamado.RESOLVIDO)


class TelasDoMoradorTests(BaseChamados):
    def setUp(self):
        super().setUp()
        self.client.login(username="ana@x.com", password="Senha-Teste-1")

    def test_acionar_ponto_mostra_o_aviso_e_o_link_do_sp156(self):
        ponto = self.ponto()
        resposta = self.client.get(reverse("chamado_acionar_ponto", args=[ponto.pk]))
        self.assertContains(resposta, "não substitui o registro oficial")
        self.assertContains(resposta, "sp156.prefeitura.sp.gov.br")
        self.assertContains(resposta, "199")

    def test_acionar_ponto_cria_chamado_e_vai_para_meus_chamados(self):
        ponto = self.ponto()
        resposta = self.client.post(
            reverse("chamado_acionar_ponto", args=[ponto.pk]),
            {"descricao": "Galho grande prestes a cair", "risco_iminente": "on"}, follow=True,
        )
        chamado = Chamado.objects.get()
        self.assertTrue(chamado.risco_iminente)
        self.assertContains(resposta, "encaminhado ao órgão")
        self.assertContains(resposta, "Encaminhado ao órgão")

    def test_ponto_de_outra_regiao_da_404(self):
        ponto = self.ponto(regiao=self.outra)
        resposta = self.client.get(reverse("chamado_acionar_ponto", args=[ponto.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_meus_chamados_lista_so_os_do_morador(self):
        self.chamado(self.ponto(descricao="Ponto da Ana"))
        bia = self.morador("bia@x.com")
        abrir_chamado(bia, self.ponto(CategoriaRisco.DRENAGEM, autor=bia, descricao="Ponto da Bia"), "da Bia")
        resposta = self.client.get(reverse("meus_chamados"))
        self.assertContains(resposta, "Preciso de ajuda")
        self.assertNotContains(resposta, "da Bia")

    def test_morador_confirma_a_resolucao_e_o_ponto_e_resolvido(self):
        ponto = self.ponto()
        chamado = self.chamado(ponto)
        self.client.post(reverse("chamado_confirmar", args=[chamado.pk]))
        chamado.refresh_from_db()
        ponto.refresh_from_db()
        self.assertEqual(chamado.status, StatusChamado.RESOLVIDO)
        self.assertEqual(chamado.resolvido_por, ResolvidoPor.MORADOR)
        self.assertEqual(ponto.status, StatusPonto.RESOLVIDO)
        resposta = self.client.post(reverse("chamado_confirmar", args=[chamado.pk]), follow=True)
        self.assertContains(resposta, "já foi encerrado")

    def test_outro_morador_nao_confirma_o_chamado_alheio(self):
        chamado = self.chamado()
        self.morador("bia@x.com")
        self.client.login(username="bia@x.com", password="Senha-Teste-1")
        resposta = self.client.post(reverse("chamado_confirmar", args=[chamado.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_pedir_ajuda_em_tarefa_cria_ponto_chamado_e_escala_a_tarefa(self):
        self.modelo("Limpar grade")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        tarefa = Tarefa.objects.get(usuario=self.ana)
        dados = {"categoria": "DRENAGEM", "descricao": "Bueiro grande entupido, não consigo limpar",
                 "endereco": "Rua Exemplo, 200", "risco_iminente": "on", **DENTRO}
        self.client.post(reverse("chamado_pedir_ajuda", args=[tarefa.pk]), dados)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.ESCALADA)
        chamado = Chamado.objects.get()
        self.assertEqual(chamado.tarefa, tarefa)
        self.assertEqual(chamado.ponto.categoria, "DRENAGEM")
        self.assertEqual(chamado.destinatario.nome, "Subprefeitura")

    def test_pedir_ajuda_fora_da_regiao_nao_cria_nada_e_a_tarefa_continua_pendente(self):
        self.modelo("Limpar grade")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        tarefa = Tarefa.objects.get(usuario=self.ana)
        dados = {"categoria": "DRENAGEM", "descricao": "x", **FORA}
        resposta = self.client.post(reverse("chamado_pedir_ajuda", args=[tarefa.pk]), dados)
        self.assertContains(resposta, "fora da sua região")
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.PENDENTE)
        self.assertEqual(PontoDeRisco.objects.count(), 0)
        self.assertEqual(Chamado.objects.count(), 0)

    def test_tarefa_de_outro_morador_da_404(self):
        self.modelo("Limpar grade")
        bia = self.morador("bia@x.com")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        tarefa_da_bia = Tarefa.objects.get(usuario=bia)
        resposta = self.client.get(reverse("chamado_pedir_ajuda", args=[tarefa_da_bia.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_telas_exigem_login(self):
        self.client.logout()
        for nome in ("meus_chamados",):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 302)


class SemRetornoTests(BaseChamados):
    def test_marca_sem_retorno_apos_72_horas_do_encaminhamento(self):
        antigo = self.chamado(self.ponto(descricao="antigo"))
        recente = self.chamado(self.ponto(CategoriaRisco.DRENAGEM, descricao="recente"))
        Chamado.objects.filter(pk=antigo.pk).update(encaminhado_em=self.agora - timedelta(hours=73))
        Chamado.objects.filter(pk=recente.pk).update(encaminhado_em=self.agora - timedelta(hours=71))
        self.assertEqual(verificar_sem_retorno(self.agora), 1)
        antigo.refresh_from_db()
        recente.refresh_from_db()
        self.assertEqual(antigo.status, StatusChamado.SEM_RETORNO)
        self.assertEqual(recente.status, StatusChamado.ENCAMINHADO)

    def test_chamado_encerrado_nao_vira_sem_retorno(self):
        chamado = self.chamado()
        registrar_acao(chamado, "RESOLVIDO")
        Chamado.objects.update(encaminhado_em=self.agora - timedelta(hours=100))
        self.assertEqual(verificar_sem_retorno(self.agora), 0)

    def test_comando_verificar_chamados(self):
        chamado = self.chamado()
        Chamado.objects.filter(pk=chamado.pk).update(encaminhado_em=timezone.now() - timedelta(hours=80))
        saida = StringIO()
        call_command("verificar_chamados", stdout=saida)
        self.assertIn("Sem retorno: 1", saida.getvalue())


class DestinatariosTests(Base):
    def test_comando_cria_os_tres_destinatarios_de_teste_e_nao_duplica(self):
        call_command("carregar_destinatarios", "--email", "grupo@exemplo.com", stdout=StringIO())
        call_command("carregar_destinatarios", "--email", "grupo@exemplo.com", stdout=StringIO())
        self.assertEqual(Destinatario.objects.count(), 3)
        self.assertEqual(set(Destinatario.objects.values_list("email", flat=True)), {"grupo@exemplo.com"})
        self.assertEqual(rotear("REDE_ELETRICA").tipo, TipoDestinatario.CONCESSIONARIA_ENERGIA)
        self.assertEqual(rotear("ENCOSTA").tipo, TipoDestinatario.DEFESA_CIVIL)
        self.assertEqual(rotear("ARVORE").tipo, TipoDestinatario.SUBPREFEITURA)
