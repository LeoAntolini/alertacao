from django import forms

from pontos.forms import PontoForm


class AcionarForm(forms.Form):
    descricao = forms.CharField(
        label="Explique o problema ao órgão", max_length=500,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 500}),
    )
    risco_iminente = forms.BooleanField(
        label="Há risco iminente (pode cair, alagar ou ferir alguém agora)", required=False
    )


class AjudaTarefaForm(PontoForm):
    """'Preciso de ajuda' em uma tarefa: relata o ponto e já aciona o órgão."""

    risco_iminente = forms.BooleanField(
        label="Há risco iminente (pode cair, alagar ou ferir alguém agora)", required=False
    )
