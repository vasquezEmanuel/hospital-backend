# Backend — Hospital Alma Mater · Odontología

FastAPI + SQLAlchemy 2 + PostgreSQL 16. `schema.sql` es la fuente de verdad del modelo de datos; las migraciones de
Alembic lo reproducen y el CI verifica que ambos coincidan (`scripts/check_schema_drift.py`).

## Estado
**Estado — Sprint 2:** esquema v1.2, API de pacientes y catálogo CIE-10 (búsqueda sin tildes), validación de JWT,
Swagger en `/docs` e importador ETL (`python -m etl.cli catalogo|atenciones ARCHIVO`) con cola de revisión.
Guía para mostrar el sistema: [docs/DEMO.md](docs/DEMO.md). Atenciones, imágenes y expediente: Sprint 3.

## Desarrollo local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # Swagger: http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto postgres local, base hospital_test)
```
Cambiar el modelo de datos: 1) `schema.sql`, 2) migración en `alembic/versions/`, 3) `pytest` (incluye la comprobación de drift).

## Windows (PowerShell)
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
docker compose up -d db
docker compose exec db psql -U postgres -c "CREATE DATABASE hospital_test;"   # solo la primera vez
alembic upgrade head
ruff check .
ruff format --check .
pytest
```
PowerShell 5.1 no acepta `&&`: ejecuta un comando por línea.

## Integración continua
`.github/workflows/ci.yml` corre en cada push y Pull Request: lint (ruff), pruebas sobre PostgreSQL real,
coherencia `schema.sql` ↔ migraciones y auditoría de dependencias (`pip-audit`).

## Convenciones
- Commits: `docs/COMMITS.md` (activar la plantilla con `git config commit.template .gitmessage`).
- **El repositorio es público: nunca subir datos reales** (Excel de pacientes, imágenes clínicas, `.env`).