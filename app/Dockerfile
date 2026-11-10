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
