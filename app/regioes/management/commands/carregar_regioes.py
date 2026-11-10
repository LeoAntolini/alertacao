"""Carrega as regiões-piloto do AlertAção (distritos de São Paulo).

Lê um shapefile ou GeoJSON, filtra os distritos Jardim Ângela e Capão Redondo,
converte para WGS84 (EPSG:4326) e grava/atualiza o modelo Regiao.

Exemplos (dentro do contêiner, a partir da pasta /app):
    python manage.py carregar_regioes dados/distritos.shp --listar
    python manage.py carregar_regioes dados/distritos.shp --exportar regioes/fixtures/regioes_piloto.geojson
    python manage.py carregar_regioes regioes/fixtures/regioes_piloto.geojson
"""
import json
import unicodedata
from pathlib import Path

from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import LinearRing, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError

from regioes.models import Regiao

# nome normalizado (sem acento, minúsculo) -> nome de exibição
PILOTO = {
    "jardim angela": "Jardim Ângela",
    "capao redondo": "Capão Redondo",
}
CAMPOS_NOME = ("ds_nome", "nm_distrit", "nm_distrito", "nome", "name")


def normalizar(texto):
    """'JARDIM  ÂNGELA' -> 'jardim angela'."""
    s = unicodedata.normalize("NFKD", str(texto))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(s.split())


def como_multipolygon(geos):
    if isinstance(geos, Polygon):
        return MultiPolygon(geos)
    return geos


def para_2d(geos):
    """Remove a coordenada Z, se existir (a coluna do banco é 2D)."""
    if not geos.hasz:
        return geos
    srid = geos.srid
    poligonos = []
    for poligono in geos:
        aneis = [LinearRing([(c[0], c[1]) for c in anel.coords], srid=srid) for anel in poligono]
        poligonos.append(Polygon(*aneis, srid=srid))
    return MultiPolygon(*poligonos, srid=srid)


class Command(BaseCommand):
    help = "Carrega as regiões-piloto (Jardim Ângela e Capão Redondo) de um shapefile ou GeoJSON."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do .shp ou .geojson (ex.: dados/distritos.shp)")
        parser.add_argument("--campo", help="Nome do campo que traz o nome do distrito")
        parser.add_argument("--encoding", default="utf-8",
                            help="Codificação do arquivo (use latin-1 se os acentos saírem errados)")
        parser.add_argument("--listar", action="store_true",
                            help="Só mostra os campos e os primeiros registros, sem gravar nada")
        parser.add_argument("--exportar",
                            help="Grava as regiões carregadas em um GeoJSON (para versionar no repositório)")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        try:
            fonte = DataSource(str(caminho), encoding=opcoes["encoding"])
        except Exception as erro:
            raise CommandError(f"Não foi possível abrir o arquivo: {erro}")
        camada = fonte[0]

        if opcoes["listar"]:
            self.stdout.write(f"Campos: {', '.join(camada.fields)}")
            self.stdout.write(f"Sistema de coordenadas: {camada.srs.name if camada.srs else 'ausente'}")
            for i, feicao in enumerate(camada):
                if i >= 5:
                    break
                self.stdout.write(str({c: feicao.get(c) for c in camada.fields}))
            return

        campo = opcoes["campo"]
        if not campo:
            mapa = {c.lower(): c for c in camada.fields}
            for candidato in CAMPOS_NOME:
                if candidato in mapa:
                    campo = mapa[candidato]
                    break
        if not campo:
            raise CommandError(
                "Não achei o campo com o nome do distrito. "
                "Rode com --listar e informe --campo NOME_DO_CAMPO."
            )
        if camada.srs is None:
            raise CommandError("O arquivo não informa o sistema de coordenadas.")

        carregadas = {}
        for feicao in camada:
            chave = normalizar(feicao.get(campo))
            if chave not in PILOTO:
                continue
            geom = feicao.geom
            geom.transform(4326)
            geos = como_multipolygon(geom.geos)
            if not geos.valid:
                geos = como_multipolygon(geos.buffer(0))
            geos = para_2d(geos)
            geos.srid = 4326
            nome = PILOTO[chave]
            regiao, criada = Regiao.objects.update_or_create(
                nome=nome,
                defaults={
                    "cidade": "São Paulo",
                    "geometria": geos,
                    "ponto_representativo": geos.point_on_surface,
                },
            )
            carregadas[nome] = regiao
            self.stdout.write(f"Região {'criada' if criada else 'atualizada'}: {nome}")

        if opcoes["exportar"] and carregadas:
            colecao = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"nome": r.nome, "cidade": r.cidade},
                        "geometry": json.loads(r.geometria.geojson),
                    }
                    for r in carregadas.values()
                ],
            }
            destino = Path(opcoes["exportar"])
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(json.dumps(colecao, ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"GeoJSON gravado em {destino}")

        faltando = [nome for nome in PILOTO.values() if nome not in carregadas]
        if faltando:
            raise CommandError(
                f"Não encontrei no arquivo: {', '.join(faltando)}. "
                "Confira o campo com --listar (e a codificação, com --encoding latin-1)."
            )
        self.stdout.write(self.style.SUCCESS(f"{len(carregadas)} regiões carregadas."))
