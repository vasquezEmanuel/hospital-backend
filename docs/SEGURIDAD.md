# Seguridad: autenticación, MFA y permisos de base de datos (Sprint 5)

Todo con Supabase (Auth + Postgres) y Render. Orden de ejecución: **cada fase se verifica antes de pasar a la siguiente**.

## Fase A · Supabase (usuarios y roles)
1. Abre `https://REF.supabase.co/auth/v1/.well-known/jwks.json`: debe mostrar al menos una clave (`"alg":"ES256"`). Si `keys` está vacío, el proyecto usa el método antiguo (HS256): avisar antes de seguir.
2. **Authentication → Sign In / Providers → Email**: apaga *Allow new users to sign up*.
3. **Authentication → Users → Add user → Create new user** (marca *Auto Confirm User*): `emanuelfeb10+odontologo@gmail.com` y `emanuelfeb10+admin@gmail.com`, con contraseñas fuertes guardadas en privado.
4. Roles (en `app_metadata`, que el usuario no puede editar). SQL Editor:
```sql
update auth.users set raw_app_meta_data = coalesce(raw_app_meta_data,'{}'::jsonb) || '{"roles":["odontologo"]}'::jsonb
 where email = 'emanuelfeb10+odontologo@gmail.com';
update auth.users set raw_app_meta_data = coalesce(raw_app_meta_data,'{}'::jsonb) || '{"roles":["administrador"]}'::jsonb
 where email = 'emanuelfeb10+admin@gmail.com';
select email, raw_app_meta_data from auth.users order by email;
```
5. **Project Settings → API Keys**: copia la *publishable key* (o la `anon` si es lo que muestra). Es pública por diseño; no se sube al repositorio.

## Fase B · Código
Copiar los archivos del sprint, `ruff format .`, `ruff check .`, `pytest --cov=app --cov-fail-under=80` (esperado: `172 passed`), commit y push. El CI debe quedar en verde. Render se redespliega solo y todo sigue funcionando igual (aún no cambia ninguna variable).

## Fase C · Render: validar los tokens de Supabase (MFA todavía apagado)
Render → tu servicio → **Environment**. Agrega o edita:

| Variable | Valor |
|---|---|
| `AUTH_ISSUER` | `https://REF.supabase.co/auth/v1` |
| `AUTH_AUDIENCE` | `authenticated` |
| `AUTH_JWKS_URL` | `https://REF.supabase.co/auth/v1/.well-known/jwks.json` |
| `AUTH_ALGORITHMS` | `ES256` |
| `AUTH_ROLES_CLAIM` | `app_metadata.roles` |
| `AUTH_REQUIRE_MFA` | `false` (por ahora) |

**Borra `AUTH_JWT_SECRET`** (con almacenamiento S3 ya no se necesita y así ningún token de prueba vuelve a funcionar). **Save, rebuild, and deploy.**

## Fase D · Postman: iniciar sesión
1. Importa `Hospital_API_Demo.postman_collection.json` (elige **Replace** si Postman pregunta; borra la colección anterior si quedó duplicada).
2. Colección → **Variables**, columna **Current value** (no Initial): `supabase_key` (la clave pública), `password_odontologo`, `password_admin`. Verifica `supabase_url` y los dos correos. **Save**.
3. Carpeta **A**: `A.1 Iniciar sesión (odontólogo)` → 200 y *Rol odontologo dentro del token*. Repite con el administrador.
4. Prueba `2.1 Registrar paciente`: debe responder 201 con el token de Supabase (aún aal1).

## Fase E · MFA (segundo factor)
Por cada usuario (primero odontólogo, luego administrador):
1. `A.1` iniciar sesión.
2. `A.3 Inscribir la app autenticadora` (**solo la primera vez**): la respuesta trae `totp.secret`. En Google/Microsoft Authenticator o Authy: *Añadir cuenta → Ingresar clave de configuración* y pega el secreto.
3. Escribe el código de 6 dígitos de la app en la variable `codigo_mfa_odontologo` (o `_admin`), Current value.
4. `A.4 Pedir reto MFA` y, enseguida, `A.5 Verificar código MFA`: *Token con segundo factor (aal2)* en verde. El token nuevo queda guardado.
5. Cada sesión nueva: `A.1`, `A.4`, `A.5` (el token dura 1 hora por defecto).

Cuando ambos tengan aal2, en Render pon `AUTH_REQUIRE_MFA=true` y redespliega. Comprobación: con un token recién iniciado (`A.1`, aal1) las peticiones dan **403 "Se requiere verificación en dos pasos (MFA)"**; después de `A.4`+`A.5` dan 200.

## Fase F · Usuario de base de datos restringido
1. Abre `docs/sql/seguridad_bd.sql`, cambia `CAMBIAR_ESTA_CONTRASENA` por una contraseña larga de **solo letras y números** y guárdala.
2. Supabase → **SQL Editor** → pega todo el archivo → **Run**. Debe terminar sin error (repetirlo es seguro).
3. Render → **Environment**:
   - `MIGRATIONS_DATABASE_URL` = la cadena que hoy tienes en `DATABASE_URL` (usuario `postgres`).
   - `DATABASE_URL` = `postgresql://hospital_api.REF:CONTRASEÑA_NUEVA@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require` (en el pooler el usuario lleva el sufijo `.REF`).
4. Redespliega y recorre la colección completa: todo debe seguir en verde. Si el log dice `Tenant or user not found`, revisa el sufijo `.REF` del usuario.

Qué NO puede hacer ahora la API aunque se filtren sus credenciales: borrar o vaciar tablas (`DELETE`/`TRUNCATE`), cambiar el esquema, modificar o borrar auditoría, ni escribir en el catálogo CIE-10. Las migraciones y el ETL siguen con el usuario `postgres`.

## Fase G · CORS
`CORS_ORIGINS` en Render = dominios del front separados por coma (p. ej. `https://app.hospital.example`). Sin front aún, déjalo vacío. Postman no usa CORS.

## Antes de pasar a `ENVIRONMENT=production`
La API **se niega a arrancar** en producción si falta cualquiera de: `DOCS_ENABLED=false`, `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_REQUIRE_MFA=true`, `STORAGE_BACKEND=s3`, `CORS_ORIGINS` sin `*`. El error lista lo que falta.

## Problemas frecuentes
| Síntoma | Causa |
|---|---|
| 401 con token de Supabase | `AUTH_ISSUER`/`AUDIENCE`/`JWKS_URL` mal escritos; token vencido (1 h) |
| 403 "Rol insuficiente" | el usuario no tiene `app_metadata.roles` (Fase A, paso 4) o `AUTH_ROLES_CLAIM` no es `app_metadata.roles` |
| 403 "Se requiere verificación en dos pasos" | token aal1: repetir `A.4` y `A.5` |
| A.5 da error | código vencido (cambia cada 30 s) o reto vencido: repetir `A.4` y escribir un código nuevo |
| `permission denied` en los logs tras la Fase F | una escritura nueva no está en el script: añadirla (sección 2 y 4) |
