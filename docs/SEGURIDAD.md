# Seguridad: autenticación, roles y permisos de base de datos (Sprint 5)

Cómo se protege la API:

- **Quién entra:** el front inicia sesión en Supabase Auth con correo y contraseña. Supabase entrega un token (JWT). La API lo valida con las claves públicas de Supabase y lee el rol de `app_metadata.roles`. Roles: `odontologo` y `administrador`.
- **Qué puede hacer la base de datos:** la API se conecta con un usuario restringido (`hospital_api`) que no puede borrar tablas, cambiar el esquema ni tocar la auditoría.
- **Producción:** con `ENVIRONMENT=production` la API no arranca si la configuración es insegura (ver al final).
- **Segundo factor (MFA):** existe en el código pero está **apagado por decisión del equipo** (sección final).

## 1 · Supabase

1. Abre `https://oqqmchuzsqknmgtnfadu.supabase.co/auth/v1/.well-known/jwks.json`: debe mostrar `"alg":"ES256"`. Si `keys` sale vacío, el proyecto usa el método antiguo: avisa.
2. **Authentication → Sign In / Providers → Email:** apaga **Allow new users to sign up** (los usuarios los crea un administrador).
3. **Authentication → Users → Add user → Create new user**, con **Auto Confirm User**. Hoy existen:
   - `hospital.backend1+odontologo@gmail.com`
   - `hospital.backend1+admin@gmail.com`
4. **SQL Editor →** asigna los roles (van en `app_metadata`, que el usuario no puede editar) y comprueba:
   ```sql
   update auth.users set raw_app_meta_data = coalesce(raw_app_meta_data,'{}'::jsonb) || '{"roles":["odontologo"]}'::jsonb
    where email = 'hospital.backend1+odontologo@gmail.com';
   update auth.users set raw_app_meta_data = coalesce(raw_app_meta_data,'{}'::jsonb) || '{"roles":["administrador"]}'::jsonb
    where email = 'hospital.backend1+admin@gmail.com';
   select email, raw_app_meta_data from auth.users order by email;
   ```
   El `select` debe mostrar `"roles":["odontologo"]` y `"roles":["administrador"]`.
5. **Project Settings → API Keys:** la clave **publishable** (o anon) es pública y la usa el front. La `service_role` jamás va en el front ni en Render.

### Agregar a una persona nueva (p. ej. la Dra. Alvarez)
Repite los pasos 3 y 4 con su correo (`"odontologo"` o `"administrador"`). Ella debe cerrar sesión y volver a entrar para que su token traiga el rol.

## 2 · Render → Environment

| Variable | Valor |
|---|---|
| `AUTH_ISSUER` | `https://oqqmchuzsqknmgtnfadu.supabase.co/auth/v1` |
| `AUTH_AUDIENCE` | `authenticated` |
| `AUTH_JWKS_URL` | `https://oqqmchuzsqknmgtnfadu.supabase.co/auth/v1/.well-known/jwks.json` |
| `AUTH_ALGORITHMS` | `ES256` |
| `AUTH_ROLES_CLAIM` | `app_metadata.roles` |
| `AUTH_REQUIRE_MFA` | `false` |
| `CORS_ORIGINS` | dominios del front, ver `docs/CONEXION_FRONT.md` |
| `AUTH_JWT_SECRET` | **borrada** |

Después: **Save, rebuild, and deploy** hasta **Live**.

## 3 · Usuario de base de datos restringido (`hospital_api`)

1. Abre `docs/sql/seguridad_bd.sql` y cambia `CAMBIAR_ESTA_CONTRASENA` por una contraseña larga de **solo letras y números**. Guárdala.
2. Supabase → **SQL Editor** → pega todo el archivo → **Run**. Debe terminar sin error (repetirlo es seguro).
3. Render → **Environment**:
   - `MIGRATIONS_DATABASE_URL` = el valor que hoy tiene `DATABASE_URL` (usuario `postgres`).
   - `DATABASE_URL` = `postgresql://hospital_api.oqqmchuzsqknmgtnfadu:CONTRASEÑA@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require`
4. Redespliega. Cuando esté **Live**, abre `https://hospital-backend-43np.onrender.com/health/ready`: debe responder bien.

Lo que la API **no** puede hacer aunque se filtren sus credenciales: borrar o vaciar tablas, cambiar el esquema, modificar o borrar auditoría, ni escribir en el catálogo CIE-10. Las migraciones y el ETL corren con `postgres`.

## 4 · Antes de pasar a `ENVIRONMENT=production`
La API **se niega a arrancar** si falta algo de: `DOCS_ENABLED=false`, `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `STORAGE_BACKEND=s3`, `CORS_ORIGINS` solo con dominios `https://` (sin `*` ni `localhost`). El error del log lista lo que falta.

## 5 · Problemas frecuentes
| Síntoma | Causa |
|---|---|
| 401 | token vencido (1 h) o `AUTH_ISSUER`/`AUDIENCE`/`JWKS_URL` mal escritos |
| 403 "Rol insuficiente" | el usuario no tiene `app_metadata.roles` (sección 1, paso 4) o falta volver a iniciar sesión |
| `Tenant or user not found` en el log | el usuario de `DATABASE_URL` no lleva el sufijo `.oqqmchuzsqknmgtnfadu` |
| `permission denied` en el log | una escritura nueva no está en `docs/sql/seguridad_bd.sql` |

## 6 · Segundo factor (MFA): apagado
El equipo decidió no exigirlo por ahora. El soporte sigue en el código (`AUTH_REQUIRE_MFA`, desactivado) y se puede encender sin cambios: activar TOTP en Supabase (*Authentication → Sign In / Providers → Multi-Factor*), que el front incluya las pantallas de inscripción y de código, y poner `AUTH_REQUIRE_MFA=true`. El Documento Técnico (6.5) contempla MFA: no tenerlo es una **desviación que debe validarse con la Dra. Alvarez**, porque entonces la contraseña es lo único que protege los datos de los pacientes (usar contraseñas largas y únicas).
