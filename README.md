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
