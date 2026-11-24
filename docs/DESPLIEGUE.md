# Despliegue de demostración: Render + Supabase

Objetivo: tener la API en internet, con base de datos real y datos **sintéticos**, para demostrar el backend.
Render ejecuta el contenedor (`Dockerfile`); Supabase aloja PostgreSQL. Las migraciones se aplican solas al arrancar.

## 0. Antes de desplegar
El CI de GitHub debe estar en verde (`pytest`, `ruff`, deriva de esquema, `pip-audit`).

## 1. Supabase (base de datos)
1. Crea un proyecto. Guarda la **contraseña de la base de datos**: usa solo letras y números (si lleva `@ : / # %`,
   hay que codificarla en la URL).
2. Pulsa **Connect** → pestaña **Session pooler** y copia la cadena. Tiene esta forma:
   `postgresql://postgres.REFPROYECTO:CONTRASEÑA@aws-0-REGION.pooler.supabase.com:5432/postgres`
3. **Usa el Session pooler (puerto 5432), no la conexión directa**: la directa es IPv6 y Render no tiene IPv6 saliente.
   Tampoco el Transaction pooler (6543): no admite sentencias preparadas, que usa el driver.
4. Añade al final `?sslmode=require`. Ese texto completo es tu `DATABASE_URL`.

## 2. Render (API)
1. **New → Web Service** → conecta el repo `hospital-backend` (rama `main`).
2. **Language/Runtime: Docker** (detecta el `Dockerfile`). **Instance type: Free**. Región cercana a la de Supabase.
3. **Health Check Path:** `/health`
4. **Environment Variables:**

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la cadena del paso 1 |
| `AUTH_JWT_SECRET` | secreto aleatorio de 40+ caracteres (ver abajo) |
| `ENVIRONMENT` | `staging` |
| `DOCS_ENABLED` | `true` |
| `PUBLIC_BASE_URL` | `https://NOMBRE-DE-TU-SERVICIO.onrender.com` (sin `/` final) |

Generar el secreto (PowerShell):
```powershell
$b = New-Object byte[] 36; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)
```
5. **Create Web Service.** En los logs del primer despliegue se ve `alembic upgrade head` creando las tablas y después
   `Uvicorn running`. Comprueba `https://TU-SERVICIO.onrender.com/health`, `/health/ready` y `/docs`.
   Si `PUBLIC_BASE_URL` tenía un nombre distinto al real, corrígela y Render redespliega.

## 3. Cerrar la API de datos de Supabase (obligatorio)
Supabase expone por defecto las tablas del esquema `public` a través de su propia API REST. Con datos de salud eso no
puede quedar abierto. En **SQL Editor** ejecuta, una vez que Render haya creado las tablas:
```sql
DO $$ DECLARE t record; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
END $$;
```
Sin políticas, nadie entra por esa API; el backend sigue funcionando porque se conecta con el rol `postgres`.
Repite este bloque cuando una migración nueva cree tablas. (Opcional: apagar la Data API en *Project Settings*.)

## 4. Cargar datos de demostración (desde tu PC, hacia Supabase)
En PowerShell, en la carpeta del repo y con el entorno virtual activo:
```powershell
$env:DATABASE_URL = "LA-CADENA-DEL-PASO-1"
python -m scripts.generar_datos_demo
python -m etl.cli catalogo   datos_demo\catalogo_cie10_demo.xlsx
python -m etl.cli atenciones datos_demo\atenciones_demo.xlsx
Remove-Item Env:DATABASE_URL
```
Esperado: 5 códigos odontológicos; 6 atenciones insertadas, 1 omitida, 5 a revisión. La última línea es necesaria: con
`DATABASE_URL` apuntando a Supabase, `pytest` intentaría crear una base de pruebas allí.

## 5. Tokens de demostración (rol odontólogo y rol administrador)
Deben firmarse con el **mismo** `AUTH_JWT_SECRET` que pusiste en Render:
```powershell
$env:AUTH_JWT_SECRET = "EL-MISMO-SECRETO-DE-RENDER"
$env:ENVIRONMENT = "staging"
$TOKEN = python -m scripts.generar_token
$ADMIN = python -m scripts.generar_token --rol administrador --sub demo-admin --horas 4
Remove-Item Env:AUTH_JWT_SECRET, Env:ENVIRONMENT
```

## 6. Demostrar el backend
**a) Recorrido automático** (imprime cada paso con OK/FALLA):
```powershell
python -m scripts.demo_api --url https://TU-SERVICIO.onrender.com --token $TOKEN --admin-token $ADMIN
```
**b) En vivo con Swagger:** abre `https://TU-SERVICIO.onrender.com/docs` → **Authorize** → pega `$TOKEN` →
prueba los endpoints del guion.

| Qué mostrar | Petición | Demuestra |
|---|---|---|
| Seguridad | cualquier endpoint sin token | `401` |
| Búsqueda tolerante | `GET /api/v1/pacientes?q=maria` | encuentra "María" sin tildes |
| Catálogo | `GET /api/v1/cie10?odontologico=true` | 5 códigos odontológicos (regla 2) |
| Imágenes | `POST /api/v1/imagenes` (archivo + `id_paciente`, un UUID) | regla 4; devuelve enlace firmado y temporal (regla 7) |
| Paciente → enfermedades e imágenes | `GET /api/v1/pacientes/{id_paciente}/expediente` (UUID) | búsqueda por paciente |
| Enfermedad → pacientes | `GET /api/v1/enfermedades/C187/pacientes?en=hospitalizacion` y `K021?en=bucal` | búsqueda por enfermedad |
| Auditoría | `GET /api/v1/auditoria` con `$ADMIN` | regla 6; con `$TOKEN` responde `403` (roles del IdP) |

## 7. Antes de presentar
- Render gratis **duerme el servicio tras ~15 min sin tráfico**; la primera petición tarda ~1 min. Abre `/health` unos minutos antes.
- Las imágenes se guardan en el disco temporal de Render: se pierden al reiniciar o redesplegar. Súbelas durante la demo.
- Los tokens duran 8 h (`--horas` lo cambia).
- Los proyectos gratuitos de Supabase se pausan tras una semana sin actividad: entra al panel antes de la demo.

## Problemas frecuentes
| Síntoma | Causa y arreglo |
|---|---|
| `Network is unreachable` / error de host | usaste la conexión directa: cambia al Session pooler |
| `password authentication failed` | contraseña errada, o el usuario no es `postgres.REFPROYECTO` |
| `prepared statement ... already exists` | usaste el puerto 6543: usa 5432 |
| `/health/ready` da 503 | `DATABASE_URL` mal copiada; revisa los logs de Render |
| `401` con token válido en Swagger | el secreto del token no coincide con el de Render, o el token expiró |
| El enlace de la imagen apunta a `localhost` | falta `PUBLIC_BASE_URL` en Render |

## Qué falta para producción real (Sprint 5)
Proveedor de identidad (Auth0/Cognito/Supabase Auth) en lugar de tokens de desarrollo, `ENVIRONMENT=production`
y `DOCS_ENABLED=false`, almacenamiento S3 (añadir `boto3`), migraciones como paso de despliegue aparte, pruebas de carga.

## 7 · Gestión de cuentas de profesionales (llave de servicio)
La pestaña "Gestión de profesionales" crea usuarios en Supabase Auth desde la API. Para eso la API necesita la llave de administración de Supabase:
1. Supabase → **Project Settings → API Keys** → copia la **secret key** (antes llamada `service_role`; empieza por `sb_secret_...`). **Nunca** la pongas en el front ni en el repositorio.
2. Render → tu servicio → **Environment** → agrega `SUPABASE_SERVICE_ROLE_KEY` = esa llave. **Save, rebuild, and deploy.**
3. Sin esta variable, las rutas de cuentas responden 503 y todo lo demás funciona igual. `SUPABASE_URL` no hace falta: se deduce de `AUTH_ISSUER`.
4. Primer administrador de una instalación nueva: `docs/sql/primer_admin.sql` (una sola vez); los demás se crean desde la pantalla.
5. Supabase → **Authentication → Sign In / Providers**: deja desactivado **Allow new users to sign up** (acceso solo por invitación).
