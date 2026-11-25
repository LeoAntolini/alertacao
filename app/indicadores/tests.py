from datetime import timedelta

from django.contrib.gis.geos import Point
from django.urls import reverse

from alertas.choices import CategoriaRisco
from alertas.models import Tarefa
from alertas.servicos import publicar_alerta
from alertas.tests import Base
from chamados.models import Chamado, Destinatario, ResolvidoPor, StatusChamado, TipoDestinatario
from pontos.models import PontoDeRisco, StatusPonto

from .servicos import calcular

H = timedelta(hours=1)


class Dados(Base):
    """Cenário com resultado conhecido, para conferir com cálculo manual."""

    def setUp(self):
        super().setUp()
        self.ana = self.morador("ana@x.com")
        self.bia = self.morador("bia@x.com")
        self.modelo("M1")
        self.modelo("M2", categoria=None)
        self.pub1, self.pub2 = self.agora - 24 * H, self.agora - 2 * H

        def ponto(regiao, categoria, criado, status=StatusPonto.ATIVO, resolvido=None):
            p = PontoDeRisco.objects.create(
                regiao=regiao, categoria=categoria, descricao="x", localizacao=Point(-46.78, -23.72, srid=4326)
            )
            PontoDeRisco.objects.filter(pk=p.pk).update(criado_em=criado, status=status, resolvido_em=resolvido)
            return p

        a = self.agora
        ponto(self.regiao, CategoriaRisco.ARVORE, a - 48 * H, StatusPonto.RESOLVIDO, a - 20 * H)    # P1
        ponto(self.regiao, CategoriaRisco.ARVORE, a - 48 * H)                                          # P2
        ponto(self.regiao, CategoriaRisco.DRENAGEM, a - 48 * H, StatusPonto.RESOLVIDO, a - 30 * H)  # P3
        ponto(self.regiao, CategoriaRisco.DRENAGEM, a - 1 * H)                                         # P4

        self.a1 = self.alerta(48)   # início em +48 h; publicado há 24 h -> antecedência de 72 h
        self.a2 = self.alerta(10)   # início em +10 h; publicado há 2 h  -> antecedência de 12 h
        publicar_alerta(self.a1, self.resp, self.pub1)
        publicar_alerta(self.a2, self.resp, self.pub2)
        self.carla = self.morador("carla@x.com")  # entra depois das publicações

        t1 = list(Tarefa.objects.filter(alerta=self.a1, usuario=self.ana).order_by("modelo__titulo"))
        t1[0].concluir(self.pub1 + 3 * H)
        t1[1].concluir(self.pub1 + 5 * H)
        Tarefa.objects.filter(alerta=self.a1, usuario=self.bia).order_by("modelo__titulo").first().dispensar(self.pub1 + H)
        Tarefa.objects.filter(alerta=self.a2, usuario=self.ana).order_by("modelo__titulo").first().concluir(self.pub2 + H)

        dest = Destinatario.objects.create(nome="D", tipo=TipoDestinatario.SUBPREFEITURA, email="d@x.com", categorias_atendidas=["ARVORE"])
        r2 = [ponto(self.outra, CategoriaRisco.ARVORE, a - 60 * H, StatusPonto.RESOLVIDO, a - 40 * H),
              ponto(self.outra, CategoriaRisco.ARVORE, a - 60 * H),
              ponto(self.outra, CategoriaRisco.ARVORE, a - 60 * H)]
        for i, (p, kw) in enumerate(zip(r2, [
            {"status": StatusChamado.RESOLVIDO, "resolvido_em": a - 40 * H, "resolvido_por": ResolvidoPor.DESTINATARIO},
            {"status": StatusChamado.EM_ATENDIMENTO, "em_atendimento_em": a - 10 * H},
            {"status": StatusChamado.ENCAMINHADO},
        ])):
            Chamado.objects.create(
                autor=self.ana, ponto=p, destinatario=dest, descricao="x", token_hash=f"hash{i}",
                token_expira_em=a + timedelta(days=30), encaminhado_em=a - 50 * H, **kw,
            )


class IndicadoresTests(Dados):
    def test_resumo(self):
        d = calcular(30, self.agora)
        self.assertEqual((d["alertas_publicados"], d["tarefas_concluidas"], d["chamados_abertos"]), (2, 3, 3))

    def test_i1_antecedencia_media(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i1"], 42.0)

    def test_i2_adesao_ao_plano_exclui_as_dispensadas(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i2"], 3 / 7 * 100)

    def test_i3_pontos_tratados_antes_do_evento(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i3"], 1 / 3 * 100)

    def test_i4_tempo_medio_de_resolucao_de_chamados(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i4"], 10.0)

    def test_i5_retorno_do_destinatario(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i5"], 2 / 3 * 100)

    def test_i6_cobertura_de_notificacao(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i6"], 4 / 6 * 100)

    def test_i7_concentracao_de_riscos_ativos(self):
        d = calcular(30, self.agora)
        por_regiao = {(i["regiao"], i["categoria"]): i["n"] for i in d["i7"]}
        self.assertEqual(por_regiao, {("R1", "ARVORE"): 1, ("R1", "DRENAGEM"): 1, ("R2", "ARVORE"): 2})

    def test_i8_tempo_ate_concluir_a_tarefa(self):
        self.assertAlmostEqual(calcular(30, self.agora)["i8"], 3.0)

    def test_periodo_deixa_de_fora_alertas_antigos(self):
        from alertas.models import Alerta
        Alerta.objects.filter(pk=self.a1.pk).update(publicado_em=self.agora - timedelta(days=60))
        self.assertEqual(calcular(30, self.agora)["alertas_publicados"], 1)
        self.assertEqual(calcular(90, self.agora)["alertas_publicados"], 2)

    def test_sem_dados_retorna_none(self):
        Alerta = self.a1.__class__
        Alerta.objects.all().delete()
        Chamado.objects.all().delete()
        d = calcular(30, self.agora)
        for chave in ("i1", "i2", "i3", "i4", "i5", "i6", "i8"):
            self.assertIsNone(d[chave])


class PainelTests(Dados):
    def test_morador_recebe_403_e_a_tentativa_e_registrada(self):
        self.client.login(username="ana@x.com", password="Senha-Teste-1")
        with self.assertLogs("alertacao.seguranca", level="WARNING"):
            resposta = self.client.get(reverse("painel"))
        self.assertEqual(resposta.status_code, 403)

    def test_responsavel_ve_os_indicadores(self):
        self.client.login(username="resp@x.com", password="Senha-Teste-1")
        resposta = self.client.get(reverse("painel"))
        self.assertEqual(resposta.status_code, 200)
        for trecho in ("Antecedência média dos alertas", "Adesão ao plano", "Cobertura de notificação",
                       "I7 · Concentração de riscos ativos", "alertas publicados"):
            self.assertContains(resposta, trecho)

    def test_periodo_invalido_usa_30_dias(self):
        self.client.login(username="resp@x.com", password="Senha-Teste-1")
        self.assertEqual(self.client.get(reverse("painel"), {"dias": "abc"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("painel"), {"dias": "5"}).status_code, 200)

    def test_exige_login(self):
        self.assertEqual(self.client.get(reverse("painel")).status_code, 302)
