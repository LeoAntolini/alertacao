# AlertAção

Plataforma comunitária (PWA) de prevenção de desastres: transforma avisos de risco em um plano de prevenção por região, reúne pontos de risco em um mapa colaborativo e permite acionar o órgão responsável por e-mail com link seguro.

Projeto da Avaliação 3 (A3) de Engenharia de Software. Linha: Computação Aplicada ao Meio Ambiente e Recursos Naturais. ODS 11 e 13.

> Aviso preventivo comunitário: não substitui alertas oficiais da Defesa Civil. Em risco iminente, ligue 199 (Defesa Civil) ou 193 (Bombeiros). Para registro oficial, ligue 156 ou use o portal SP156.

## Integrantes

| Nome completo | RA | Papel principal |
| --- | --- | --- |
| Bryan Matos | 825134014 | Requisitos |
| Leonardo Antolini de Oliveira | 824125434 | Gerenciamento, implementação e documentação |
| Marcos Vinicius Silveira da Silva | 824123862 | Modelagem e arquitetura |

Todos os integrantes acompanharam o desenvolvimento; os commits estão na conta de Leonardo, responsável pelo código.

Repositório: https://github.com/LeoAntolini/alertacao (privado; o professor precisa ser adicionado como colaborador)

## Demonstração

- Site: https://alertacao.onrender.com (o plano gratuito dorme após 15 minutos; a primeira requisição leva cerca de 1 minuto)
- Vídeo: [link do vídeo]

## Funcionalidades do MVP

- Alerta manual por região, com estágios: previsão (mais de 72 h), preparação (24 a 72 h) e iminente (menos de 24 h)
- Plano de prevenção: tarefas que o morador conclui, dispensa ou pede ajuda
- Mapa de pontos de risco dentro da região do morador
- Chamado ao órgão responsável por e-mail, com link seguro e acompanhamento de status
- Notificações na caixa de entrada e por e-mail
- Painel de indicadores I1 a I8 para o responsável pelo sistema

Fica para a Fase 2: foto no relato, confirmação de pontos por outros moradores, exclusão de conta, sugestão automática de alerta (Open-Meteo), reforço por estágio, SMS e Cell Broadcast, painel para órgãos, ONGs.

## Tecnologias

Python e Django 5.2 (GeoDjango), PostgreSQL com PostGIS, Leaflet 1.9.4 com tiles OpenStreetMap, Docker e docker compose, Gunicorn e WhiteNoise, Argon2. Implantação: Neon (banco) e Render (aplicação).

## Como rodar localmente

Pré-requisitos: Docker e docker compose.

1. Copie `.env.example` para `.env` e ajuste os valores.
2. Suba o ambiente:

       docker compose up --build

3. Em outro terminal, prepare os dados:

       docker compose exec web python manage.py migrate
       docker compose exec web python manage.py carregar_regioes regioes/fixtures/regioes_piloto.geojson
       docker compose exec web python manage.py carregar_modelos_tarefa
       docker compose exec web python manage.py carregar_destinatarios
       docker compose exec web python manage.py createsuperuser

4. Abra http://localhost:8000. O administrador fica em `/admin/`.

### Testes

    docker compose exec web python manage.py test

### Comandos de manutenção

| Comando | O que faz |
| --- | --- |
| `enviar_notificacoes` | Envia as notificações pendentes por e-mail |
| `verificar_chamados` | Marca chamados sem retorno após 72 h e reenvia e-mails em aberto |
| `encerrar_alertas` | Encerra alertas vencidos e expira tarefas |

### E-mail

Sem configuração, os e-mails vão para o log (backend de console), o que basta para a demonstração. Para e-mail real, defina `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` e `DEFAULT_FROM_EMAIL`.

## Implantação na nuvem

Veja `README_implantacao.md`. Nunca coloque segredos no repositório. Verificação de saúde: `GET /saude/`.

## Estrutura

    app/
      config/        configurações e rotas
      usuarios/      cadastro, login, papéis e interface base
      regioes/       regiões com geometria
      alertas/       alertas, modelos de tarefa e plano de prevenção
      notificacoes/  notificações
      pontos/        mapa e pontos de risco
      chamados/      chamados e link seguro do destinatário
      indicadores/   painel I1 a I8
    docs/            documentação técnica, diagramas e roteiro da demonstração

## Documentação

- Documentação técnica (estrutura da A3)
- Documento-Base v2.2 e planilha da Etapa 3 (requisitos e rastreabilidade)
- Diagramas de casos de uso, classes e sequência
- Roteiro da demonstração

## Fluxo de trabalho

Branches por funcionalidade, integração por pull request na `main` e quadro Kanban no GitHub Projects.
