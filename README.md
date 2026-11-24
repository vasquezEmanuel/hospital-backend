# Backend — Hospital Alma Mater · Odontología

API REST del área de odontología del Hospital Alma Mater. Integra tres fuentes de información que antes se cruzaban a
mano —el catálogo de enfermedades **CIE-10**, las **atenciones de pacientes** y las **imágenes clínicas**— y permite
consultarlas en ambos sentidos: de una enfermedad a los pacientes que la tienen, y de un paciente a sus enfermedades e
imágenes.

| | |
|---|---|
| **Aplicación web** | https://gestion-imagenes-odontologicas.vercel.app |
| **API en producción** | https://hospital-backend-43np.onrender.com · estado: [`/health`](https://hospital-backend-43np.onrender.com/health) |
| **Equipo** | Steven Alipio Berrio · Robert Alexander Blandón Rincón · Emanuel Vásquez Yepes |
| **Contraparte clínica** | Dra. Gloria Alvarez, coordinadora del área de odontología |

La aplicación es de uso interno: las cuentas las crea un administrador y no existe registro público.

## Funcionalidades
- **Pacientes y expediente:** identificación única por documento, ubicación por departamento y municipio (códigos DANE),
  historial de atenciones, diagnósticos e imágenes.
- **Atenciones:** fecha, aseguradora, profesional, plan de tratamiento, tratamientos y observaciones; diagnósticos
  bucales (cada uno con uno o varios códigos CIE-10 odontológicos) y diagnóstico de hospitalización.
- **Imágenes clínicas:** subida individual y en lote, asociadas al paciente y, opcionalmente, a una atención o diagnóstico.
- **Búsqueda por enfermedad**, reportes exportables a Excel y resumen de inicio.
- **Importación** de CIE-10, atenciones e imágenes existentes, con cola de revisión para filas dudosas.
- **Gestión de profesionales y cuentas** con dos roles: `odontologo` y `administrador`.

## Modelo de datos
`schema.sql` (PostgreSQL 16) es la fuente de verdad; las migraciones de Alembic lo reproducen y la integración continua
verifica que ambos coincidan.

- `paciente` — identificado por su documento; ubicación opcional en `municipio` → `departamento` (DIVIPOLA del DANE).
- `atencion` — pertenece a un paciente; referencia aseguradora y profesional; se relaciona N:M con `tratamiento`.
- `diagnostico_bucal` ↔ `cie10` (N:M mediante `cie10_x_diagnostico_bucal`): solo admite códigos marcados como
  odontológicos, validado por la API y por un *trigger*. `diagnostico_hospitalario` es 1:1 con `cie10`.
- `imagen_clinica` — siempre asociada a un paciente; opcionalmente a una atención y a un diagnóstico bucal.
- `auditoria` — registro inmutable de toda consulta o modificación de datos de pacientes.
- `importacion` e `importacion_fila` — trazabilidad y cola de revisión de las cargas.

El rol del usuario (`odontologo`, `administrador`) no está en la base de datos: viaja como *claim* del proveedor de identidad.

## Reglas de negocio y seguridad
1. El documento de identidad identifica de forma única al paciente (puede corregirse, nunca duplicarse).
2. Todo código CIE-10 de un diagnóstico bucal debe ser odontológico; el de hospitalización puede ser cualquiera.
3. Una atención tiene cero o más diagnósticos bucales y, a lo sumo, uno de hospitalización.
4. Toda imagen queda asociada, como mínimo, al paciente.
5. Diagnósticos, imágenes, profesionales y catálogos **se inactivan, nunca se eliminan**; pacientes y atenciones no tienen `DELETE`.
6. Toda consulta o modificación de datos de pacientes queda en la auditoría, registrada antes de ejecutarse.
7. Las imágenes se entregan únicamente mediante enlaces temporales firmados.

Medidas adicionales: autenticación JWT con un proveedor OIDC gestionado (Supabase Auth); la API se conecta a la base con
un usuario de mínimo privilegio y *Row Level Security*; identificadores públicos UUID (los numéricos son internos);
CORS restringido a los dominios del front; la documentación interactiva se desactiva en producción.

## Arquitectura
| Capa | Tecnología |
|---|---|
| API y lógica de negocio | Python 3.12 · FastAPI · Pydantic |
| Acceso a datos y migraciones | SQLAlchemy 2 · Alembic |
| Base de datos | PostgreSQL 16 (Supabase) |
| Almacenamiento de imágenes | Object Storage compatible con S3 (Supabase Storage) |
| Identidad y roles | OAuth2/OIDC (Supabase Auth) |
| Despliegue | Docker · Render |

```
app/        main · core (configuración y seguridad) · db · models · schemas · routers · services · repositories · middleware
alembic/    migraciones y datos de referencia       etl/        importador de CIE-10 y atenciones
tests/      pruebas sobre PostgreSQL real           scripts/    utilidades (verificación de esquema, respaldo)
```

Capas: los *routers* validan y delegan; los *services* aplican las reglas de negocio; los *repositories* son los únicos
que consultan la base.

## API
Prefijo `/api/v1`. Todos los recursos, salvo `/health`, requieren un token válido.

| Recurso | Contenido |
|---|---|
| `/pacientes`, `/pacientes/{id}/expediente` | Alta, búsqueda, ficha, edición y expediente completo |
| `/atenciones`, `/diagnosticos-bucales` | Atenciones, edición y diagnósticos de cada una |
| `/imagenes`, `/archivos` | Subida (individual y en lote), reasignación, baja lógica y enlaces firmados |
| `/cie10`, `/enfermedades` | Catálogo CIE-10 y búsqueda enfermedad → pacientes |
| `/departamentos`, `/municipios` | Catálogos de ubicación del DANE |
| `/aseguradoras`, `/tratamientos`, `/profesionales` | Catálogos y gestión de profesionales y sus cuentas |
| `/importaciones` | Cargas de CIE-10, atenciones e imágenes |
| `/reportes`, `/inicio` | Reportes exportables y resumen |
| `/auditoria` | Consulta del registro de auditoría (administrador) |

El contrato completo se publica en `/docs` cuando `DOCS_ENABLED=true`.

## Calidad
- Pruebas automatizadas sobre PostgreSQL real, con cobertura superior al 95 % (umbral de CI: 80 %).
- La base de pruebas se construye con `alembic upgrade head`, de modo que cada ejecución valida también las migraciones.
- Integración continua (`.github/workflows/ci.yml`): lint con `ruff`, pruebas con cobertura, coherencia
  `schema.sql` ↔ migraciones y auditoría de dependencias con `pip-audit`.

## Ejecución local
```bash
docker compose up -d db
cp .env.example .env && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000/docs
pytest                            # usa TEST_DATABASE_URL (por defecto, base local hospital_test)
```
En Windows (PowerShell 5.1, que no acepta `&&`) cada comando va en su propia línea; el entorno virtual se activa con
`.\.venv\Scripts\Activate.ps1`.

Cambios de modelo: primero `schema.sql`, luego una migración en `alembic/versions/` y por último `pytest`, que incluye
la comprobación de coherencia entre ambos.

## Documentación
| Documento | Contenido |
|---|---|
| [docs/CONEXION_FRONT.md](docs/CONEXION_FRONT.md) | Consumo de la API: autenticación, endpoints, errores |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Despliegue del servicio |
| [docs/SEGURIDAD.md](docs/SEGURIDAD.md) | Modelo de seguridad, roles y permisos de la base de datos |
| [docs/COPIAS_DE_SEGURIDAD.md](docs/COPIAS_DE_SEGURIDAD.md) | Respaldo y restauración |
| [docs/ETL.md](docs/ETL.md) | Importación de datos |
| [docs/COMMITS.md](docs/COMMITS.md) | Convención de commits |

## Alcance
El análisis de imágenes con *machine learning* (diagnóstico preliminar automático) es una línea futura y queda fuera de
este proyecto.
