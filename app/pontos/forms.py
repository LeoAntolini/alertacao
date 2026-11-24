from django import forms
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from alertas.choices import CategoriaRisco

LIMITE_PRECISAO_GPS_M = 100  # RNF04


class PontoForm(forms.Form):
    categoria = forms.ChoiceField(label="Tipo de risco", choices=CategoriaRisco.choices)
    descricao = forms.CharField(
        label="O que você viu? (até 500 caracteres)", max_length=500,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 500}),
    )
    endereco = forms.CharField(label="Referência (rua, número ou ponto conhecido)", max_length=255, required=False)
    latitude = forms.FloatField(min_value=-90, max_value=90, widget=forms.HiddenInput, required=False)
    longitude = forms.FloatField(min_value=-180, max_value=180, widget=forms.HiddenInput, required=False)
    precisao_metros = forms.FloatField(min_value=0, widget=forms.HiddenInput, required=False)

    def __init__(self, *args, regiao=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.regiao = regiao
        self.ponto = None

    def clean(self):
        dados = super().clean()
        latitude, longitude = dados.get("latitude"), dados.get("longitude")
        if latitude is None or longitude is None:
            raise ValidationError("Marque o local do risco no mapa ou use a localização do aparelho.")
        precisao = dados.get("precisao_metros")
        if precisao is not None and precisao > LIMITE_PRECISAO_GPS_M:
            raise ValidationError(
                f"A precisão do GPS está ruim (cerca de {round(precisao)} m). Ajuste o ponto tocando no mapa."
            )
        ponto = Point(longitude, latitude, srid=4326)
        if not self.regiao.geometria.contains(ponto):  # RN15
            raise ValidationError(
                f"O local marcado fica fora da sua região ({self.regiao.nome}). "
                "Marque um ponto dentro da linha azul do mapa."
            )
        self.ponto = ponto
        return dados
