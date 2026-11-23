FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Bibliotecas de sistema exigidas pelo GeoDjango (GDAL, GEOS, PROJ) e pelo PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
        binutils gdal-bin libgdal-dev libgeos-dev libproj-dev libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Arquivos estáticos (painel administrativo) para o WhiteNoise servir em produção.
# As variáveis abaixo existem só para o settings.py carregar durante o build.
RUN POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build python manage.py collectstatic --noinput

# Produção: aplica as migrações e sobe o servidor. No docker compose local,
# o "command" do docker-compose.yml substitui esta linha.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 60"]
