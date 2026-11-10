from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from django.urls import reverse

from regioes.models import Regiao

from .models import Papel, Usuario

SENHA = "SenhaSegura-2026"


def quadrado(x0, y0, lado=0.05):
    return Polygon(
        ((x0, y0), (x0, y0 + lado), (x0 + lado, y0 + lado), (x0 + lado, y0), (x0, y0)), srid=4326
    )


def dados_validos(**extra):
    dados = {
        "nome": "Maria Souza",
        "email": "Maria@Exemplo.com",
        "senha1": SENHA,
        "senha2": SENHA,
        "endereco": "Rua Exemplo, 100",
        "latitude": "-23.72",
        "longitude": "-46.78",
        "consentimento": "on",
    }
    dados.update(extra)
    return dados


class CadastroTests(TestCase):
    def setUp(self):
        self.regiao = Regiao.objects.create(
            nome="Região de Teste", geometria=MultiPolygon(quadrado(-46.80, -23.75), srid=4326)
        )
        self.url = reverse("cadastro")

    def test_cadastro_valido_cria_morador_na_regiao_e_faz_login(self):
        resposta = self.client.post(self.url, dados_validos())
        self.assertRedirects(resposta, reverse("inicio"))
        usuario = Usuario.objects.get(email="maria@exemplo.com")
        self.assertEqual(usuario.papel, Papel.MORADOR)
        self.assertEqual(usuario.regiao, self.regiao)
        self.assertIsNotNone(usuario.consentimento_em)
        self.assertIn("_auth_user_id", self.client.session)

    def test_senha_e_guardada_com_hash_argon2(self):
        self.client.post(self.url, dados_validos())
        usuario = Usuario.objects.get(email="maria@exemplo.com")
        self.assertTrue(usuario.password.startswith("argon2$"))
        self.assertNotIn(SENHA, usuario.password)

    def test_local_fora_das_regioes_e_recusado(self):
        resposta = self.client.post(self.url, dados_validos(latitude="-23.55", longitude="-46.63"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "fora das regiões atendidas")
        self.assertEqual(Usuario.objects.count(), 0)

    def test_gps_com_precisao_ruim_pede_ajuste_manual(self):
        resposta = self.client.post(self.url, dados_validos(precisao_metros="300"))
        self.assertContains(resposta, "precisão do GPS")
        self.assertEqual(Usuario.objects.count(), 0)

    def test_gps_com_boa_precisao_e_aceito(self):
        self.client.post(self.url, dados_validos(precisao_metros="20"))
        self.assertEqual(Usuario.objects.count(), 1)

    def test_sem_localizacao_e_recusado(self):
        self.client.post(self.url, dados_validos(latitude="", longitude=""))
        self.assertEqual(Usuario.objects.count(), 0)

    def test_sem_consentimento_e_recusado(self):
        dados = dados_validos()
        del dados["consentimento"]
        self.client.post(self.url, dados)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_senhas_diferentes_sao_recusadas(self):
        self.client.post(self.url, dados_validos(senha2="outra-senha-123"))
        self.assertEqual(Usuario.objects.count(), 0)

    def test_senha_fraca_e_recusada(self):
        self.client.post(self.url, dados_validos(senha1="123", senha2="123"))
        self.assertEqual(Usuario.objects.count(), 0)

    def test_email_repetido_e_recusado_sem_diferenciar_maiusculas(self):
        self.client.post(self.url, dados_validos())
        self.client.logout()
        resposta = self.client.post(self.url, dados_validos(email="MARIA@exemplo.com"))
        self.assertContains(resposta, "Já existe uma conta")
        self.assertEqual(Usuario.objects.count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="ana@exemplo.com", email="ana@exemplo.com", password=SENHA, nome="Ana"
        )

    def test_login_valido_ignora_maiusculas_no_email(self):
        resposta = self.client.post(reverse("login"), {"username": "ANA@exemplo.com", "password": SENHA})
        self.assertRedirects(resposta, reverse("inicio"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_invalido_nao_autentica(self):
        resposta = self.client.post(reverse("login"), {"username": "ana@exemplo.com", "password": "errada"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pagina_inicial_exige_login(self):
        resposta = self.client.get(reverse("inicio"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta["Location"])

    def test_logout_encerra_a_sessao(self):
        self.client.login(username="ana@exemplo.com", password=SENHA)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sessao_expira_em_24_horas(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 24 * 60 * 60)


class SuperusuarioTests(TestCase):
    def test_superusuario_vira_responsavel_pelo_sistema(self):
        admin = Usuario.objects.create_superuser(
            username="adm@exemplo.com", email="adm@exemplo.com", password=SENHA, nome="Adm"
        )
        self.assertEqual(admin.papel, Papel.RESPONSAVEL_SISTEMA)
