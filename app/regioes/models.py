import uuid

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point


class Regiao(models.Model):
    """Polígono de um distrito (ou subdivisão menor) monitorado pelo AlertAção (D08)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=120, unique=True)
    cidade = models.CharField(max_length=120, default="São Paulo")
    geometria = models.MultiPolygonField(srid=4326)
    # Ponto dentro do polígono, usado para consultar a previsão do tempo (RF08).
    # Se ficar vazio, é calculado ao salvar.
    ponto_representativo = models.PointField(srid=4326, blank=True)

    class Meta:
        verbose_name = "região"
        verbose_name_plural = "regiões"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.cidade})"

    def contem(self, ponto: Point) -> bool:
        """True se o ponto está dentro da região (base da RN01)."""
        return self.geometria.contains(ponto)

    def save(self, *args, **kwargs):
        if self.ponto_representativo is None and self.geometria is not None:
            self.ponto_representativo = self.geometria.point_on_surface
        super().save(*args, **kwargs)
