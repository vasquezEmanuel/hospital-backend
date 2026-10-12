# Backend — Hospital Alma Mater · Odontología

FastAPI + SQLAlchemy 2 + PostgreSQL 16. `schema.sql` es la fuente de verdad del modelo de datos; las migraciones de
Alembic lo reproducen y el CI verifica que ambos coincidan (`scripts/check_schema_drift.py`).

**Estado — Sprint 1:** esquema v1.2 (0001 base · 0002 ajustes del front · 0003 tratamientos/importador), API de
pacientes y catálogo CIE-10, validación de JWT, Swagger en `/docs`. Auditoría y permisos finos: Sprint 4.

## Desarrollo local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # Swagger: http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto postgres local, base hospital_test)
```
Cambiar el modelo de datos: 1) `schema.sql`, 2) migración en `alembic/versions/`, 3) `pytest` (incluye la comprobación de drift).

## Despliegue (un repo, un servicio, una base)
1. **GitHub:** repo privado en tu cuenta. Secret `DATABASE_URL` (Settings → Secrets and variables → Actions).
2. **Base de datos:** proyecto en Supabase; usar la cadena del *pooler en modo sesión* como `DATABASE_URL`.
3. **API:** Web Service en Render desde el repo, lenguaje Docker, *Health Check Path* `/health`,
   *Auto-Deploy* = **After CI checks pass**. Variables: las de `.env.example` (`DOCS_ENABLED=false` en producción).

Cada push a `main`: CI → migraciones → Render despliega. Los PR solo corren el CI.
