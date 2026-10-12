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
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
