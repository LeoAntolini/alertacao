from django.contrib.gis.geos import Point
from django.urls import reverse

from alertas.choices import CategoriaRisco
from alertas.tests import Base
from usuarios.models import Papel, Usuario

from .models import PontoDeRisco, StatusPonto

DENTRO = {"latitude": "-23.72", "longitude": "-46.78"}   # dentro do quadrado de R1
FORA = {"latitude": "-23.55", "longitude": "-46.63"}     # dentro de R2


def dados(**extra):
    d = {"categoria": CategoriaRisco.DRENAGEM, "descricao": "Bueiro entupido em frente ao número 100",
         "endereco": "Rua Exemplo, 100", **DENTRO}
    d.update(extra)
    return d


class RelatarTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        self.url = reverse("ponto_novo")

    def test_relato_valido_registra_ponto_ativo_na_regiao_e_vai_para_o_mapa(self):
        resposta = self.client.post(self.url, dados(), follow=True)
        ponto = PontoDeRisco.objects.get()
        self.assertEqual(ponto.regiao, self.regiao)
        self.assertEqual(ponto.autor, self.ana)
        self.assertEqual(ponto.status, StatusPonto.ATIVO)
        self.assertEqual(ponto.categoria, CategoriaRisco.DRENAGEM)
        self.assertAlmostEqual(ponto.localizacao.y, -23.72, places=5)
        self.assertAlmostEqual(ponto.localizacao.x, -46.78, places=5)
        self.assertContains(resposta, "Risco registrado")
        self.assertContains(resposta, "Bueiro entupido")

    def test_descricao_acima_de_500_caracteres_e_recusada(self):
        self.client.post(self.url, dados(descricao="x" * 501))
        self.assertEqual(PontoDeRisco.objects.count(), 0)

    def test_descricao_de_500_caracteres_e_aceita(self):
        self.client.post(self.url, dados(descricao="x" * 500))
        self.assertEqual(PontoDeRisco.objects.count(), 1)

    def test_categoria_invalida_e_recusada(self):
        self.client.post(self.url, dados(categoria="OUTRA"))
        self.assertEqual(PontoDeRisco.objects.count(), 0)

    def test_local_fora_da_regiao_do_morador_e_recusado(self):
        resposta = self.client.post(self.url, dados(**FORA))
        self.assertContains(resposta, "fora da sua região")
        self.assertEqual(PontoDeRisco.objects.count(), 0)

    def test_sem_localizacao_e_recusado(self):
        self.client.post(self.url, dados(latitude="", longitude=""))
        self.assertEqual(PontoDeRisco.objects.count(), 0)

    def test_gps_com_precisao_ruim_pede_ajuste_e_boa_precisao_e_aceita(self):
        resposta = self.client.post(self.url, dados(precisao_metros="300"))
        self.assertContains(resposta, "precisão do GPS")
        self.assertEqual(PontoDeRisco.objects.count(), 0)
        self.client.post(self.url, dados(precisao_metros="20"))
        self.assertEqual(PontoDeRisco.objects.count(), 1)

    def test_exige_login(self):
        self.client.logout()
        for resposta in (self.client.get(self.url), self.client.post(self.url, dados())):
            self.assertEqual(resposta.status_code, 302)
            self.assertIn(reverse("login"), resposta["Location"])
        self.assertEqual(PontoDeRisco.objects.count(), 0)

    def test_usuario_sem_regiao_volta_para_o_inicio(self):
        self.client.logout()
        self.client.login(username="resp@x.com", password="Senha-Teste-1")
        resposta = self.client.get(self.url)
        self.assertRedirects(resposta, reverse("inicio"), fetch_redirect_response=False)


class MapaTests(Base):
    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.bia = self.morador("bia@x.com")
        self.client.login(username="ana@x.com", password="Senha-Teste-1")

    def ponto(self, descricao, categoria=CategoriaRisco.DRENAGEM, regiao=None, status=StatusPonto.ATIVO, autor=None):
        return PontoDeRisco.objects.create(
            autor=autor or self.bia, regiao=regiao or self.regiao, categoria=categoria, descricao=descricao,
            localizacao=Point(-46.78, -23.72, srid=4326), status=status,
        )

    def test_mostra_so_pontos_ativos_da_regiao_do_morador(self):
        self.ponto("Ponto ativo daqui")
        self.ponto("Ponto resolvido", status=StatusPonto.RESOLVIDO)
        self.ponto("Ponto de outra regiao", regiao=self.outra)
        resposta = self.client.get(reverse("mapa"))
        self.assertContains(resposta, "Ponto ativo daqui")
        self.assertNotContains(resposta, "Ponto resolvido")
        self.assertNotContains(resposta, "Ponto de outra regiao")

    def test_filtro_por_categoria_oculta_as_demais(self):
        self.ponto("Bueiro entupido", categoria=CategoriaRisco.DRENAGEM)
        self.ponto("Encosta com rachadura", categoria=CategoriaRisco.ENCOSTA)
        resposta = self.client.get(reverse("mapa"), {"categoria": CategoriaRisco.ENCOSTA})
        self.assertContains(resposta, "Encosta com rachadura")
        self.assertNotContains(resposta, "Bueiro entupido")

    def test_categoria_desconhecida_no_filtro_mostra_todos(self):
        self.ponto("Bueiro entupido")
        resposta = self.client.get(reverse("mapa"), {"categoria": "QUALQUER"})
        self.assertContains(resposta, "Bueiro entupido")

    def test_nao_exibe_a_autoria_do_ponto(self):
        self.ponto("Ponto da Bia", autor=self.bia)
        resposta = self.client.get(reverse("mapa"))
        self.assertContains(resposta, "Ponto da Bia")
        self.assertNotContains(resposta, "bia@x.com")

    def test_mostra_a_atribuicao_do_mapa_e_a_regiao(self):
        resposta = self.client.get(reverse("mapa"))
        self.assertContains(resposta, "OpenStreetMap contributors")
        self.assertContains(resposta, "Riscos em R1")

    def test_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("mapa"))
        self.assertEqual(resposta.status_code, 302)

    def test_responsavel_sem_regiao_volta_para_o_inicio(self):
        self.client.logout()
        self.client.login(username="resp@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("mapa"))
        self.assertRedirects(resposta, reverse("inicio"), fetch_redirect_response=False)


class ResolverTests(Base):
    def test_resolver_registra_estado_e_data_e_nao_repete(self):
        ponto = PontoDeRisco.objects.create(
            regiao=self.regiao, categoria=CategoriaRisco.ARVORE, descricao="x",
            localizacao=Point(-46.78, -23.72, srid=4326),
        )
        ponto.resolver(self.agora)
        ponto.refresh_from_db()
        self.assertEqual(ponto.status, StatusPonto.RESOLVIDO)
        self.assertEqual(ponto.resolvido_em, self.agora)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            ponto.resolver(self.agora)
