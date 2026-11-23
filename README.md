# Backend — Hospital Alma Mater · Odontología

API REST del área de odontología: integra el catálogo CIE-10, pacientes/atenciones e imágenes clínicas, con búsqueda
bidireccional (enfermedad → pacientes; paciente → enfermedades e imágenes).

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 (Supabase) · Supabase Auth (JWT) y Storage ·
despliegue en Render. `schema.sql` es la fuente de verdad del modelo de datos; las migraciones de Alembic lo reproducen y
el CI verifica que ambos coincidan (`scripts/check_schema_drift.py`).

## Qué hace (estado actual)
- **Pacientes** (identificados por documento), **expediente** y **atenciones** con diagnósticos bucales (CIE-10
  odontológicos, N:M) y de hospitalización, tratamientos y profesional.
- **Imágenes clínicas** (subida individual y en lote), siempre con enlaces temporales firmados.
- **Búsqueda por enfermedad** y por paciente, **reportes** (exportación a Excel) y pantalla de **inicio**.
- **Importación** por API de CIE-10, atenciones e imágenes, con cola de revisión de filas dudosas.
- **Cuentas y roles:** `odontologo` y `administrador`, gestionados por el administrador (alta de profesionales con cuenta,
  contraseña, rol, baja que bloquea el acceso).
- **Auditoría** de toda consulta o modificación de datos de pacientes (solo el administrador la consulta).
- **Bajas lógicas:** diagnósticos, imágenes, profesionales y catálogos se inactivan, nunca se borran. Pacientes y
  atenciones no tienen `DELETE` (son historia clínica).

## Documentación
| Documento | Para qué |
|---|---|
| [docs/CONEXION_FRONT.md](docs/CONEXION_FRONT.md) | Guía para el front: variables, login, endpoints, errores frecuentes (sec. 8.1: bajas y ediciones) |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Supabase + Render, llave de servicio |
| [docs/SEGURIDAD.md](docs/SEGURIDAD.md) | Roles, rol de base de datos `hospital_api`, pasar a producción |
| [docs/COPIAS_DE_SEGURIDAD.md](docs/COPIAS_DE_SEGURIDAD.md) | Respaldos de base e imágenes y cómo restaurar |
| [docs/ETL.md](docs/ETL.md) | Importación de CIE-10 y atenciones |
| [docs/sql/seguridad_bd.sql](docs/sql/seguridad_bd.sql) | Permisos mínimos de la API (se vuelve a ejecutar cuando un sprint agrega escrituras) |
| [docs/COMMITS.md](docs/COMMITS.md) | Convención de commits |

La documentación interactiva (`/docs`) está desactivada en producción (`DOCS_ENABLED=false`).

## Producción (resumen)
Variables en Render: `ENVIRONMENT=production`, `DOCS_ENABLED=false`, `DATABASE_URL` (usuario `hospital_api`),
`CORS_ORIGINS` (solo dominios `https://` del front, sin barra final), `AUTH_*` de Supabase y, para gestionar cuentas,
`SUPABASE_SERVICE_ROLE_KEY` (solo en Render, nunca en el front ni en el repositorio). Detalle en
[docs/SEGURIDAD.md](docs/SEGURIDAD.md) y [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## Desarrollo local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # Swagger: http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto postgres local, base hospital_test)
```
Cambiar el modelo de datos: 1) `schema.sql`, 2) migración en `alembic/versions/`, 3) `pytest` (incluye la comprobación de drift).
Si el cambio agrega escrituras para la API, también `docs/sql/seguridad_bd.sql` y `tests/test_rol_api.py`.

### Windows (PowerShell)
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

## Estructura
```
app/        main, core (config/seguridad), db, models, schemas, routers, services, repositories, middleware
alembic/    migraciones          etl/   importador de CIE-10 y atenciones      functions/  indexación de imágenes
tests/      pruebas (PostgreSQL real, cobertura ≥ 80 %)                         scripts/    utilidades (respaldo, drift)
```

## Integración continua
`.github/workflows/ci.yml` corre en cada push y Pull Request: lint (ruff), pruebas sobre PostgreSQL real,
coherencia `schema.sql` ↔ migraciones y auditoría de dependencias (`pip-audit`).

## Convenciones
- Commits: `docs/COMMITS.md` (activar la plantilla con `git config commit.template .gitmessage`).
- **El repositorio es público: nunca subir datos reales** (Excel de pacientes, imágenes clínicas, `.env`, respaldos).
- Fuera de alcance: análisis de imágenes con machine learning (línea futura).
