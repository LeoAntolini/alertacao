import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from regioes.management.commands.carregar_regioes import normalizar
from regioes.models import Regiao


def quadrado(x0, y0, lado=0.05):
    return Polygon(
        ((x0, y0), (x0, y0 + lado), (x0 + lado, y0 + lado), (x0 + lado, y0), (x0, y0)),
        srid=4326,
    )


def feicao(nome, poligono):
    return {
        "type": "Feature",
        "properties": {"ds_nome": nome},
        "geometry": {"type": "Polygon", "coordinates": [[list(c) for c in poligono.coords[0]]]},
    }


class NormalizarTests(SimpleTestCase):
    def test_remove_acentos_caixa_e_espacos_extras(self):
        self.assertEqual(normalizar("JARDIM  ÂNGELA"), "jardim angela")
        self.assertEqual(normalizar("Capão Redondo"), "capao redondo")


class RegiaoTests(TestCase):
    def setUp(self):
        self.regiao = Regiao.objects.create(
            nome="Teste", geometria=MultiPolygon(quadrado(-46.80, -23.75), srid=4326)
        )

    def test_ponto_representativo_e_calculado_e_fica_dentro_da_regiao(self):
        self.assertIsNotNone(self.regiao.ponto_representativo)
        self.assertTrue(self.regiao.contem(self.regiao.ponto_representativo))

    def test_contem_ponto_dentro(self):
        self.assertTrue(self.regiao.contem(Point(-46.78, -23.72, srid=4326)))

    def test_nao_contem_ponto_fora(self):
        self.assertFalse(self.regiao.contem(Point(-46.60, -23.55, srid=4326)))

    def test_consulta_espacial_encontra_a_regiao_do_ponto(self):
        achadas = Regiao.objects.filter(geometria__contains=Point(-46.78, -23.72, srid=4326))
        self.assertEqual([r.nome for r in achadas], ["Teste"])


class CarregarRegioesTests(TestCase):
    def _gravar_arquivo(self, pasta):
        arquivo = Path(pasta) / "distritos.geojson"
        colecao = {
            "type": "FeatureCollection",
            "features": [
                feicao("JARDIM ÂNGELA", quadrado(-46.80, -23.75)),
                feicao("CAPÃO REDONDO", quadrado(-46.75, -23.75)),
                feicao("MOOCA", quadrado(-46.60, -23.55)),
            ],
        }
        arquivo.write_text(json.dumps(colecao, ensure_ascii=False), encoding="utf-8")
        return arquivo

    def test_carrega_somente_as_regioes_piloto(self):
        with tempfile.TemporaryDirectory() as pasta:
            call_command("carregar_regioes", str(self._gravar_arquivo(pasta)), stdout=StringIO())
        self.assertEqual(
            set(Regiao.objects.values_list("nome", flat=True)), {"Jardim Ângela", "Capão Redondo"}
        )

    def test_rodar_duas_vezes_nao_duplica(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = str(self._gravar_arquivo(pasta))
            call_command("carregar_regioes", arquivo, stdout=StringIO())
            call_command("carregar_regioes", arquivo, stdout=StringIO())
        self.assertEqual(Regiao.objects.count(), 2)

    def test_ponto_cai_na_regiao_certa(self):
        with tempfile.TemporaryDirectory() as pasta:
            call_command("carregar_regioes", str(self._gravar_arquivo(pasta)), stdout=StringIO())
        regiao = Regiao.objects.get(geometria__contains=Point(-46.78, -23.72, srid=4326))
        self.assertEqual(regiao.nome, "Jardim Ângela")
