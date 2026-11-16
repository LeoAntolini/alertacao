from datetime import timedelta
from io import StringIO

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from regioes.models import Regiao
from usuarios.models import Papel, Usuario

from .choices import CategoriaRisco, EstagioAlerta, Evento, NivelAlerta, StatusAlerta, StatusTarefa
from .models import Alerta, ModeloTarefa, Tarefa
from .servicos import publicar_alerta


def quadrado(x0, y0, lado=0.05):
    return Polygon(
        ((x0, y0), (x0, y0 + lado), (x0 + lado, y0 + lado), (x0 + lado, y0), (x0, y0)), srid=4326
    )


class Base(TestCase):
    def setUp(self):
        self.agora = timezone.now()
        self.regiao = Regiao.objects.create(nome="R1", geometria=MultiPolygon(quadrado(-46.80, -23.75), srid=4326))
        self.outra = Regiao.objects.create(nome="R2", geometria=MultiPolygon(quadrado(-46.60, -23.55), srid=4326))
        self.resp = Usuario.objects.create_user(
            username="resp@x.com", email="resp@x.com", password="Senha-Teste-1", nome="Resp",
            papel=Papel.RESPONSAVEL_SISTEMA,
        )

    def morador(self, email, regiao=None, ativo=True):
        return Usuario.objects.create_user(
            username=email, email=email, password="Senha-Teste-1", nome=email, papel=Papel.MORADOR,
            regiao=regiao or self.regiao, is_active=ativo,
        )

    def alerta(self, horas_ate_inicio, duracao_h=6, evento=Evento.CHUVA_FORTE, regiao=None):
        inicio = self.agora + timedelta(hours=horas_ate_inicio)
        return Alerta.objects.create(
            regiao=regiao or self.regiao, evento=evento, nivel=NivelAlerta.MODERADO,
            janela_inicio=inicio, janela_fim=inicio + timedelta(hours=duracao_h), mensagem="Teste",
        )

    def modelo(self, titulo, evento=Evento.CHUVA_FORTE, categoria=CategoriaRisco.DRENAGEM, ativo=True):
        return ModeloTarefa.objects.create(evento=evento, categoria=categoria, titulo=titulo, instrucao="x", ativo=ativo)


class EstagioTests(Base):
    def test_estagio_pela_antecedencia(self):
        casos = [
            (120, EstagioAlerta.PREVISAO), (73, EstagioAlerta.PREVISAO),
            (72, EstagioAlerta.PREPARACAO), (48, EstagioAlerta.PREPARACAO), (24, EstagioAlerta.PREPARACAO),
            (23, EstagioAlerta.IMINENTE), (12, EstagioAlerta.IMINENTE),
        ]
        for horas, esperado in casos:
            with self.subTest(horas=horas):
                self.assertEqual(self.alerta(horas).estagio(self.agora), esperado)


class PublicarTests(Base):
    def test_gera_uma_tarefa_por_morador_e_por_modelo_do_evento(self):
        self.morador("a@x.com")
        self.morador("b@x.com")
        self.morador("fora@x.com", regiao=self.outra)
        self.modelo("M1")
        self.modelo("M2", categoria=None)
        self.modelo("V1", evento=Evento.VENTANIA, categoria=None)
        resultado = publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual((resultado.moradores, resultado.tarefas), (2, 4))
        self.assertEqual(Tarefa.objects.count(), 4)
        self.assertFalse(Tarefa.objects.filter(usuario__email="fora@x.com").exists())
        self.assertFalse(Tarefa.objects.filter(usuario=self.resp).exists())

    def test_modelo_desativado_nao_gera_tarefa(self):
        self.morador("a@x.com")
        self.modelo("M1")
        self.modelo("M2", ativo=False)
        resultado = publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual(resultado.tarefas, 1)

    def test_categorias_arvore_e_rede_eletrica_nao_geram_tarefa(self):
        self.morador("a@x.com")
        ModeloTarefa.objects.create(evento=Evento.CHUVA_FORTE, categoria=CategoriaRisco.ARVORE, titulo="A", instrucao="x")
        ModeloTarefa.objects.create(evento=Evento.CHUVA_FORTE, categoria=CategoriaRisco.REDE_ELETRICA, titulo="B", instrucao="x")
        self.modelo("OK")
        resultado = publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual(resultado.tarefas, 1)

    def test_morador_inativo_nao_recebe_tarefa(self):
        self.morador("a@x.com")
        self.morador("inativo@x.com", ativo=False)
        self.modelo("M1")
        resultado = publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual((resultado.moradores, resultado.tarefas), (1, 1))

    def test_registra_estado_data_autor_e_estagio(self):
        alerta = self.alerta(12)
        publicar_alerta(alerta, self.resp, self.agora)
        alerta.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.PUBLICADO)
        self.assertEqual(alerta.publicado_em, self.agora)
        self.assertEqual(alerta.publicado_por, self.resp)
        self.assertEqual(alerta.ultimo_estagio_notificado, EstagioAlerta.IMINENTE)
        self.assertEqual(alerta.antecedencia(), timedelta(hours=12))

    def test_morador_nao_pode_publicar(self):
        alerta = self.alerta(48)
        with self.assertRaises(PermissionDenied):
            publicar_alerta(alerta, self.morador("a@x.com"), self.agora)
        alerta.refresh_from_db()
        self.assertEqual(alerta.status, StatusAlerta.RASCUNHO)

    def test_janela_invalida_e_recusada_e_nada_e_gerado(self):
        self.morador("a@x.com")
        self.modelo("M1")
        invalidas = {
            "fim igual ao início": self.alerta(48, duracao_h=0),
            "início no passado": self.alerta(-2),
            "início além de 7 dias": self.alerta(24 * 8),
        }
        for nome, alerta in invalidas.items():
            with self.subTest(nome):
                with self.assertRaises(ValidationError):
                    publicar_alerta(alerta, self.resp, self.agora)
                alerta.refresh_from_db()
                self.assertEqual(alerta.status, StatusAlerta.RASCUNHO)
        self.assertEqual(Tarefa.objects.count(), 0)

    def test_nao_publica_duas_vezes(self):
        alerta = self.alerta(48)
        publicar_alerta(alerta, self.resp, self.agora)
        with self.assertRaises(ValidationError):
            publicar_alerta(alerta, self.resp, self.agora)

    def test_regiao_sem_moradores_publica_sem_tarefas(self):
        self.modelo("M1")
        resultado = publicar_alerta(self.alerta(48), self.resp, self.agora)
        self.assertEqual((resultado.moradores, resultado.tarefas), (0, 0))


class ModeloTarefaTests(Base):
    def test_arvore_e_rede_eletrica_sao_recusadas(self):
        for categoria in (CategoriaRisco.ARVORE, CategoriaRisco.REDE_ELETRICA):
            with self.subTest(categoria=categoria):
                modelo = ModeloTarefa(evento=Evento.VENTANIA, categoria=categoria, titulo="T", instrucao="x")
                with self.assertRaises(ValidationError):
                    modelo.full_clean()

    def test_drenagem_encosta_e_sem_categoria_sao_aceitas(self):
        for i, categoria in enumerate((CategoriaRisco.DRENAGEM, CategoriaRisco.ENCOSTA, None)):
            with self.subTest(categoria=categoria):
                ModeloTarefa(evento=Evento.CHUVA_FORTE, categoria=categoria, titulo=f"T{i}", instrucao="x").full_clean()


class TarefaTests(Base):
    def _tarefa(self):
        self.morador("a@x.com")
        self.modelo("M1")
        publicar_alerta(self.alerta(48), self.resp, self.agora)
        return Tarefa.objects.get()

    def test_concluir_registra_estado_e_data_e_nao_e_reversivel(self):
        tarefa = self._tarefa()
        tarefa.concluir(self.agora)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusTarefa.CONCLUIDA)
        self.assertEqual(tarefa.concluida_em, self.agora)
        with self.assertRaises(ValidationError):
            tarefa.concluir(self.agora)
        with self.assertRaises(ValidationError):
            tarefa.dispensar(self.agora)

    def test_dispensar_e_expirar(self):
        tarefa = self._tarefa()
        tarefa.dispensar(self.agora)
        self.assertEqual(Tarefa.objects.get().status, StatusTarefa.DISPENSADA)
        tarefa.status = StatusTarefa.PENDENTE
        tarefa.save()
        tarefa.expirar(self.agora)
        self.assertEqual(Tarefa.objects.get().status, StatusTarefa.EXPIRADA)


class CatalogoTests(TestCase):
    def test_carrega_os_dez_modelos_e_pode_rodar_de_novo(self):
        call_command("carregar_modelos_tarefa", stdout=StringIO())
        call_command("carregar_modelos_tarefa", stdout=StringIO())
        self.assertEqual(ModeloTarefa.objects.count(), 10)
        self.assertEqual(ModeloTarefa.objects.filter(evento=Evento.CHUVA_FORTE).count(), 7)
        self.assertEqual(ModeloTarefa.objects.filter(evento=Evento.VENTANIA).count(), 3)

    def test_catalogo_nao_tem_arvore_nem_rede_eletrica(self):
        call_command("carregar_modelos_tarefa", stdout=StringIO())
        proibidas = [CategoriaRisco.ARVORE, CategoriaRisco.REDE_ELETRICA]
        self.assertFalse(ModeloTarefa.objects.filter(categoria__in=proibidas).exists())

    def test_recarregar_nao_reativa_modelo_desativado(self):
        call_command("carregar_modelos_tarefa", stdout=StringIO())
        ModeloTarefa.objects.filter(titulo__startswith="Limpar a grade").update(ativo=False)
        call_command("carregar_modelos_tarefa", stdout=StringIO())
        self.assertFalse(ModeloTarefa.objects.get(titulo__startswith="Limpar a grade").ativo)
