# Backend — Hospital Alma Mater · Odontología

API REST para el área de odontología del Hospital Alma Mater. Integra tres fuentes de información que antes se cruzaban
a mano —el catálogo de enfermedades **CIE-10**, las **atenciones de pacientes** y las **imágenes clínicas**— y permite
consultarlas en ambos sentidos: de una enfermedad a los pacientes que la tienen, y de un paciente a sus enfermedades e
imágenes.

**Equipo:** Steven Alipio Berrio · Robert Alexander Blandón Rincón · Emanuel Vásquez Yepes.
**Contraparte clínica:** Dra. Gloria Alvarez, coordinadora del área de odontología.

## En producción
| Componente | Dirección |
|---|---|
| Aplicación web (front) | https://gestion-imagenes-odontologicas.vercel.app |
| API (este repositorio) | https://hospital-backend-43np.onrender.com · estado: [`/health`](https://hospital-backend-43np.onrender.com/health) |

El acceso es solo para personal autorizado del hospital: las cuentas las crea un administrador y no hay registro público.
La documentación interactiva de la API está desactivada en producción.

## Funcionalidades
- **Pacientes y expediente:** identificación única por documento; historial de atenciones, diagnósticos e imágenes.
- **Atenciones:** fecha, aseguradora, profesional, plan de tratamiento, tratamientos y observaciones; diagnósticos
  bucales (uno o varios códigos CIE-10 odontológicos cada uno) y diagnóstico de hospitalización.
- **Imágenes clínicas:** subida individual y en lote, asociadas al paciente y, opcionalmente, a una atención o diagnóstico.
- **Búsqueda por enfermedad**, reportes exportables a Excel y resumen de inicio.
- **Importación** de CIE-10, atenciones e imágenes existentes, con cola de revisión para filas dudosas.
- **Gestión de profesionales y cuentas** con dos roles: `odontologo` y `administrador`.

## Reglas de negocio y seguridad
- Todo código CIE-10 de un diagnóstico bucal debe estar marcado como odontológico (validado en la API y en la base de datos).
- Los diagnósticos, imágenes, profesionales y catálogos **se inactivan, nunca se eliminan**; pacientes y atenciones no se borran.
- Toda consulta o modificación de datos de pacientes queda en un registro de **auditoría** inmutable.
- Las imágenes se entregan únicamente mediante **enlaces temporales firmados**.
- Autenticación con JWT de un proveedor OIDC gestionado (Supabase Auth); los roles viajan como *claims*.
- La API se conecta a la base con un **usuario de mínimo privilegio** (sin `DELETE` sobre datos clínicos, sin cambios de
  esquema) y con Row Level Security.
- Las cuentas las crea un administrador; no hay registro público.

## Arquitectura
| Capa | Tecnología |
|---|---|
| API y lógica de negocio | Python 3.12 · FastAPI · Pydantic |
| Acceso a datos y migraciones | SQLAlchemy 2 · Alembic |
| Base de datos | PostgreSQL 16 |
| Almacenamiento de imágenes | Object Storage compatible con S3 |
| Identidad y roles | OAuth2/OIDC (Supabase Auth) |
| Despliegue | Docker |

`schema.sql` es la fuente de verdad del modelo de datos; las migraciones de Alembic lo reproducen y la integración
continua verifica que ambos coincidan.

```
app/        main · core (configuración y seguridad) · db · models · schemas · routers · services · repositories · middleware
alembic/    migraciones            etl/    importador de CIE-10 y atenciones          functions/   indexación de imágenes
tests/      pruebas sobre PostgreSQL real            scripts/   utilidades (verificación de esquema, respaldo)
```

## Documentación
| Documento | Contenido |
|---|---|
| [docs/CONEXION_FRONT.md](docs/CONEXION_FRONT.md) | Cómo consumir la API: autenticación, endpoints, errores |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Despliegue del servicio |
| [docs/SEGURIDAD.md](docs/SEGURIDAD.md) | Modelo de seguridad, roles y base de datos |
| [docs/COPIAS_DE_SEGURIDAD.md](docs/COPIAS_DE_SEGURIDAD.md) | Respaldo y restauración |
| [docs/ETL.md](docs/ETL.md) | Importación de datos |
| [docs/COMMITS.md](docs/COMMITS.md) | Convención de commits |

Con la documentación interactiva activada (`DOCS_ENABLED=true`) la API publica su especificación en `/docs`.

## Desarrollo local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto, base local hospital_test)
```
En Windows (PowerShell 5.1, que no acepta `&&`), ejecutar cada comando en una línea; el entorno virtual se activa con
`.\.venv\Scripts\Activate.ps1`.

Para cambiar el modelo de datos: primero `schema.sql`, luego una migración en `alembic/versions/` y por último `pytest`
(incluye la comprobación de que ambos coinciden).

## Integración continua
`.github/workflows/ci.yml` ejecuta en cada push y Pull Request: lint (`ruff`), pruebas con cobertura mínima sobre
PostgreSQL real, coherencia `schema.sql` ↔ migraciones y auditoría de dependencias (`pip-audit`).

## Alcance
El análisis de imágenes con *machine learning* (diagnóstico preliminar automático) es una línea futura y no forma parte
de este proyecto.

## Contribuir
Este repositorio es público y no debe contener datos reales de pacientes, imágenes clínicas, credenciales ni archivos
`.env`. Las convenciones de commits están en [docs/COMMITS.md](docs/COMMITS.md).
