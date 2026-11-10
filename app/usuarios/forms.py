from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from regioes.models import Regiao

from .models import Usuario

LIMITE_PRECISAO_GPS_M = 100  # RNF07


class CadastroForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="E-mail")
    senha1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    senha2 = forms.CharField(label="Repita a senha", widget=forms.PasswordInput)
    endereco = forms.CharField(label="Endereço ou ponto de referência", max_length=255)
    latitude = forms.FloatField(min_value=-90, max_value=90, widget=forms.HiddenInput, required=False)
    longitude = forms.FloatField(min_value=-180, max_value=180, widget=forms.HiddenInput, required=False)
    precisao_metros = forms.FloatField(min_value=0, widget=forms.HiddenInput, required=False)
    consentimento = forms.BooleanField(
        label="Aceito que meu e-mail e a localização informada sejam usados para enviar alertas da minha região.",
        error_messages={"required": "Para criar a conta é preciso aceitar o uso do e-mail e da localização."},
    )

    ponto = None
    regiao = None

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean(self):
        dados = super().clean()

        senha1, senha2 = dados.get("senha1"), dados.get("senha2")
        if senha1 and senha2 and senha1 != senha2:
            self.add_error("senha2", "As senhas não conferem.")
        elif senha1:
            try:
                validate_password(senha1)
            except ValidationError as erro:
                self.add_error("senha1", erro)

        latitude, longitude = dados.get("latitude"), dados.get("longitude")
        if latitude is None or longitude is None:
            raise ValidationError("Marque o seu local no mapa ou use a localização do aparelho.")

        precisao = dados.get("precisao_metros")
        if precisao is not None and precisao > LIMITE_PRECISAO_GPS_M:
            raise ValidationError(
                f"A precisão do GPS está ruim (cerca de {round(precisao)} m). Ajuste o ponto tocando no mapa."
            )

        ponto = Point(longitude, latitude, srid=4326)
        regiao = Regiao.objects.filter(geometria__contains=ponto).first()
        if regiao is None:
            nomes = ", ".join(Regiao.objects.values_list("nome", flat=True)) or "nenhuma região cadastrada"
            raise ValidationError(f"Este local fica fora das regiões atendidas ({nomes}).")

        self.ponto, self.regiao = ponto, regiao
        return dados


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"autofocus": True}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
