# alertacao

## Como rodar o projeto (ambiente local)

Pré-requisitos: Git, Docker Desktop (aberto) e VS Code.

1. Clone o repositório e entre na pasta.
2. Copie o arquivo de variáveis: `cp .env.example .env` (no Windows PowerShell: `copy .env.example .env`) e troque a senha e a chave.
3. Suba o ambiente: `docker compose up --build`
4. Em outro terminal, crie as tabelas: `docker compose exec web python manage.py migrate`
5. Abra http://localhost:8000

Parar: `Ctrl+C` no terminal do `docker compose up`. Apagar também o banco: `docker compose down -v`.

O arquivo `.env` guarda segredos e **nunca** deve ser commitado.

## Implantação na nuvem

- Banco: Neon (PostgreSQL com PostGIS), plano gratuito.
- Aplicação: Render (Web Service em Docker), plano gratuito. O serviço dorme após 15 minutos sem acesso e leva cerca de 1 minuto para acordar na primeira requisição.
- A cada deploy o contêiner roda `python manage.py migrate` antes de subir o servidor.
- Verificação de saúde: `GET /saude/` (não usa o banco).

### Comandos de manutenção no banco da nuvem

Crie o arquivo `.env.neon` a partir de `.env.neon.example` e rode, na raiz do repositório:

    docker compose run --rm web-neon python manage.py migrate
    docker compose run --rm web-neon python manage.py carregar_regioes regioes/fixtures/regioes_piloto.geojson
    docker compose run --rm web-neon python manage.py carregar_modelos_tarefa
    docker compose run --rm web-neon python manage.py createsuperuser

### Variáveis de ambiente do serviço (Render)

POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_SSLMODE=require,
DJANGO_SECRET_KEY, DJANGO_DEBUG=0, DJANGO_ALLOWED_HOSTS=.onrender.com,
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.onrender.com, DEMO_MODE=1, SITE_URL=https://NOME-DO-SERVICO.onrender.com.
Nunca coloque esses valores no repositório.

### E-mail

Sem configuração, os e-mails de notificação vão para o log do serviço (backend de console), o que basta para a demonstração.
Para e-mail real, defina EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER,
EMAIL_HOST_PASSWORD e DEFAULT_FROM_EMAIL com os dados de um provedor SMTP.

### Redesign visual do AlertAcao (somente templates; nenhuma view, model, rota ou teste alterado)

1) Na raiz do repositorio:  git checkout -b feature/redesign-visual
2) Extraia este zip na raiz (ele sobrescreve os 14 templates em app/*/templates/).
3) Rode:  docker compose exec web python manage.py test
   Esperado: mesma contagem de testes que antes, todos passando.
4) Abra no navegador (celular e computador): login, cadastro, inicio, plano do alerta, mapa, relatar, chamados, avisos e painel.
5) Se tudo certo:  git add -A && git commit -m "feat(ui): redesign visual completo (mobile-first, navegacao inferior, cards)"
   Depois abra o PR para main e faca o merge.

### Botao de Administracao + visual do Django admin

1) Na branch feature/redesign-visual, extraia este zip na raiz (ele sobrescreve base.html e inicio.html
   e cria app/templates/admin/base_site.html).
2) Cole o conteudo de settings_adicionar_no_fim_admin_visual.txt no FIM de app/config/settings.py.
3) docker compose exec web python manage.py test   (deve continuar tudo passando)
4) Entre com um superusuario: aparece "Administracao do sistema" no inicio e "Administracao" no menu do computador.
   Moradores comuns nao veem o botao (e /admin/ continua exigindo login de staff).
