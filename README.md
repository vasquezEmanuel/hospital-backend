# Backend — Hospital Alma Mater · Odontología

FastAPI + SQLAlchemy 2 + PostgreSQL 16. `schema.sql` es la fuente de verdad del modelo de datos; las migraciones de
Alembic lo reproducen y el CI verifica que ambos coincidan (`scripts/check_schema_drift.py`).

## Estado
- **Sprint 1 — cerrado:** esquema v1.2 (0001 base · 0002 ajustes del front · 0003 tratamientos/importador), API de
  pacientes y catálogo CIE-10, validación de JWT, Swagger en `/docs`.
- **Sprint 2 — pendiente:** ETL y carga inicial.
- **Despliegue: pendiente (Sprint 5).**

## Desarrollo local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # Swagger: http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto postgres local, base hospital_test)
```
Cambiar el modelo de datos: 1) `schema.sql`, 2) migración en `alembic/versions/`, 3) `pytest` (incluye la comprobación de drift).

## Integración continua
`.github/workflows/ci.yml` corre en cada push y Pull Request: lint (ruff), pruebas sobre PostgreSQL real,
coherencia `schema.sql` ↔ migraciones y auditoría de dependencias (`pip-audit`).

## Convenciones
- Commits: `docs/COMMITS.md` (activar la plantilla con `git config commit.template .gitmessage`).
- **El repositorio es público: nunca subir datos reales** (Excel de pacientes, imágenes clínicas, `.env`).