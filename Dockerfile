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
# Primero se aplican las migraciones (idempotente: si ya están al día no hace nada) y luego arranca la API.
# Con una sola instancia es seguro; con varias, migrar desde un paso de despliegue aparte.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
