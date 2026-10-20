# Guía de demostración (Sprint 2)

Todo con datos **sintéticos**. Nunca cargues datos reales de pacientes en un repositorio público.
Terminal: PowerShell, en la carpeta del repo y con el entorno virtual activo (`.\.venv\Scripts\Activate.ps1`).

## 0. Preparación (una vez)
```powershell
docker compose up -d db
alembic upgrade head
```
`.env` debe tener `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hospital` y un `AUTH_JWT_SECRET` de
32 caracteres o más.

## 1. Cargar datos de demostración
```powershell
python -m scripts.generar_datos_demo
python -m etl.cli catalogo  datos_demo\catalogo_cie10_demo.xlsx
python -m etl.cli atenciones datos_demo\atenciones_demo.xlsx
```
Resultado esperado de la segunda carga: 12 filas, **6 insertadas, 1 omitida (duplicada), 5 a revisión** con su motivo.
Repetir el comando no duplica nada.

## 2. Levantar la API
```powershell
uvicorn app.main:app --reload
```
Swagger: http://localhost:8000/docs · Salud: http://localhost:8000/health

## 3. Obtener un token (solo desarrollo local)
```powershell
python -m scripts.generar_token
```
Copia el texto largo que imprime.

## 4a. Con Swagger
En `/docs` pulsa **Authorize**, pega el token y confirma. Prueba `GET /api/v1/pacientes` y `GET /api/v1/cie10`.

## 4b. Con Postman
1. Nueva petición `GET http://localhost:8000/api/v1/pacientes?q=maria`
2. Pestaña **Authorization** → Type **Bearer Token** → pega el token.
3. Send. Sin token responde `401`.

## 4c. Con PowerShell
```powershell
$T = python -m scripts.generar_token
$h = @{ Authorization = "Bearer $T" }
Invoke-RestMethod -Headers $h "http://localhost:8000/api/v1/pacientes?q=maria"
Invoke-RestMethod -Headers $h "http://localhost:8000/api/v1/cie10?odontologico=true"
```

## Qué mostrar
| Petición | Demuestra |
|---|---|
| `GET /api/v1/pacientes?q=maria` | Búsqueda sin tildes: encuentra "María Rodríguez" |
| `GET /api/v1/pacientes?q=1.025.847` | Búsqueda por documento con puntos |
| `GET /api/v1/cie10?q=cronica` | Descripción sin tildes (K051) |
| `GET /api/v1/cie10?odontologico=true` | Los 5 códigos marcados por subrayado |
| Sin token | `401` |

## Qué viene después
Sprint 3: atenciones, imágenes con enlaces firmados y expediente del paciente. Sprint 4: búsqueda enfermedad →
pacientes, auditoría y permisos por rol.