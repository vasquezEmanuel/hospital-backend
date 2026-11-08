# Imagen del backend (despliegue como contenedor serverless — sección 6.4 del documento técnico).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Usuario sin privilegios
RUN useradd --system --uid 10001 appuser
USER appuser

EXPOSE 8000
# $PORT lo define la plataforma (Render/Cloud Run); 8000 por defecto en local.
# Las migraciones corren con MIGRATIONS_DATABASE_URL (usuario propietario) y la API con DATABASE_URL (usuario
# restringido hospital_api, Sprint 5). Si MIGRATIONS_DATABASE_URL no está definida, se usa DATABASE_URL.
# Con una sola instancia es seguro; con varias, migrar desde un paso de despliegue aparte.
CMD ["sh", "-c", "DATABASE_URL=\"${MIGRATIONS_DATABASE_URL:-$DATABASE_URL}\" alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
