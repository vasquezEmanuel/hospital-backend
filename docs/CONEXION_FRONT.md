# Conexión del front con la API (Supabase Auth + CORS)

Cómo hablan las tres piezas:

```
Front (otro dominio) ──(1) correo + contraseña ──────────────▶ Supabase Auth  → devuelve un token (JWT)
Front                ──(2) Authorization: Bearer <token>─────▶ API en Render  → valida el token con las claves públicas de Supabase
Front                ◀─(3) enlace temporal firmado (5 min)──── API             → el front muestra la imagen desde Supabase Storage
```

- El front **nunca** envía la contraseña a la API: solo a Supabase. La API solo recibe el token.
- **CORS** es el permiso del navegador para que el dominio del front llame a la API. Sin él, el navegador bloquea las peticiones aunque la API responda bien.

## 1. Configuración en Render (Environment)

| Variable | Valor | Para qué |
|---|---|---|
| `CORS_ORIGINS` | dominios del front separados por coma, **sin barra final**, p. ej. `https://front-hospital.vercel.app,http://localhost:5173` | Permiso CORS |
| `AUTH_ISSUER` | `https://oqqmchuzsqknmgtnfadu.supabase.co/auth/v1` | Valida de dónde viene el token |
| `AUTH_AUDIENCE` | `authenticated` | Valida a quién va dirigido |
| `AUTH_JWKS_URL` | `https://oqqmchuzsqknmgtnfadu.supabase.co/auth/v1/.well-known/jwks.json` | Claves públicas |
| `AUTH_ALGORITHMS` | `ES256` | Algoritmo de firma (ver el JSON de `AUTH_JWKS_URL`, campo `alg`) |
| `AUTH_ROLES_CLAIM` | `app_metadata.roles` | Dónde viene el rol |
| `AUTH_REQUIRE_MFA` | `false` | Segundo factor: apagado por decisión del equipo |
| `AUTH_JWT_SECRET` | **borrada** | Ya no se usa |

Reglas de `CORS_ORIGINS`:
- Cada dominio es exactamente lo que muestra la barra del navegador: `https://`, dominio y puerto si lo hay. **Sin `/` al final y sin ruta.** (El código quita la barra final por si se cuela.)
- `http://localhost:5173` solo sirve para desarrollo. En `ENVIRONMENT=production` la API **se niega a arrancar** si hay algún dominio `http://`: quítalo antes de pasar a producción.
- Nunca `*`.
- Tras cambiarla: **Save, rebuild, and deploy**.

## 2. Configuración en Supabase

1. **Authentication → Sign In / Providers → Email**: deja el correo habilitado y **desactiva "Allow new users to sign up"** (los usuarios los crea el administrador).
2. **Authentication → URL Configuration**: *Site URL* = dominio del front (solo afecta correos de recuperación de contraseña).
3. **Authentication → Users**: crea cada usuario con *Auto Confirm User* y asígnale el rol (SQL Editor):
   ```sql
   update auth.users set raw_app_meta_data = raw_app_meta_data || '{"roles":["odontologo"]}'::jsonb where email = 'CORREO';
   ```
   (`"administrador"` para el administrador.) El usuario debe cerrar sesión y entrar de nuevo para que el token traiga el rol.
4. **Project Settings → API**: el front usa solo `Project URL` y la clave **publishable/anon**. La `service_role` jamás va en el front.

## 3. Código del front (JavaScript, `@supabase/supabase-js` v2)

Variables del front: `VITE_SUPABASE_URL`, `VITE_SUPABASE_KEY` (la pública) y `VITE_API_URL=https://hospital-backend-43np.onrender.com`.

```js
import { createClient } from "@supabase/supabase-js";
export const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_KEY);
const API = import.meta.env.VITE_API_URL;

// --- Inicio y cierre de sesión ---
export async function iniciarSesion(email, password) {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
}
export const cerrarSesion = () => supabase.auth.signOut();

// --- Llamar a la API con el token vigente (la librería lo renueva sola) ---
async function api(ruta, opciones = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const r = await fetch(`${API}/api/v1${ruta}`, {
    ...opciones,
    headers: { ...opciones.headers, Authorization: `Bearer ${token}` },
  });
  if (r.status === 401) { await supabase.auth.signOut(); throw new Error("Sesión vencida"); }
  if (!r.ok) throw Object.assign(new Error("Error de la API"), { status: r.status, detalle: await r.json().catch(() => null) });
  return r.json();
}

export const listarPacientes = (q = "", page = 1) => api(`/pacientes?q=${encodeURIComponent(q)}&page=${page}&page_size=20`);
export const crearPaciente = (p) => api("/pacientes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });

// Subir imagen: FormData. NO pongas Content-Type a mano (el navegador agrega el boundary).
export function subirImagen(archivo, idPaciente, idAtencion) {
  const f = new FormData();
  f.append("archivo", archivo);
  f.append("id_paciente", idPaciente);
  if (idAtencion) f.append("id_atencion", idAtencion);
  return api("/imagenes", { method: "POST", body: f });
}

// Cada imagen trae `url`: enlace firmado que caduca en `url_expira_en_segundos` (300). Úsalo directo en <img src>.
// No lo guardes: vuelve a pedir el listado cuando caduque.
export const imagenesDePaciente = (idPaciente) => api(`/imagenes?id_paciente=${idPaciente}`);
```

Formas de respuesta que el front debe esperar:
- Listados: `{ "items": [...], "total": N, "page": 1, "page_size": 20 }`.
- Imagen: `id_imagen`, `id_paciente`, `paciente_nombre`, `nombre_archivo`, `fecha_carga`, `url`, `url_expira_en_segundos`, `activo`.
- Errores: 401 sin sesión o token vencido (volver al login); 403 `"Rol insuficiente"` (el usuario no tiene rol asignado); 404/409/422 con un mensaje en `detail`.

## 4. Cosas que suelen fallar

| Síntoma en el navegador | Causa | Solución |
|---|---|---|
| `blocked by CORS policy: No 'Access-Control-Allow-Origin'` | el dominio no está en `CORS_ORIGINS`, tiene barra final o falta `https://`; o la API aún no redespliegó | corregir la variable y redesplegar; revisar que sea idéntico a la barra del navegador |
| El mismo error pero solo en la primera petición del día | el plan gratuito de Render duerme el servicio (~1 min al despertar) | reintentar; en el front mostrar "Conectando…" y llamar a `GET /health` al cargar |
| 401 | token vencido (1 h) o `AUTH_ISSUER`/`AUTH_AUDIENCE`/`AUTH_JWKS_URL` mal escritos | volver a iniciar sesión; revisar variables |
| 403 "Rol insuficiente" | el usuario no tiene `app_metadata.roles` | paso 4 de la sección 2 y volver a entrar |
| Subida de imagen da 422 | falta `archivo` o `id_paciente`, o se puso `Content-Type` a mano | usar `FormData` sin cabecera `Content-Type` |
| La imagen no carga | el enlace caducó (5 min) | volver a pedir el listado |

## 5. Orden recomendado para integrar

1. Conectar login, listar pacientes, crear paciente y subir imagen.
2. Cuando el front esté desplegado: agregar su dirección `https://...` a `CORS_ORIGINS`.
3. Al pasar a producción: `CORS_ORIGINS` solo con `https://`, `DOCS_ENABLED=false`, `ENVIRONMENT=production`.
