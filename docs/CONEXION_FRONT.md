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

## 4. Identificadores: siempre UUID (cambio del Sprint 6)

La API **no usa números** para identificar nada. Pacientes, atenciones, diagnósticos bucales e imágenes se identifican con un **UUID** (p. ej. `9f1c3d52-7a64-4e0b-8f2d-5c3a1b7e6d22`). Un número (`/pacientes/12`) responde **422**.

| Dónde aparece | Antes | Ahora |
|---|---|---|
| Rutas: `/pacientes/{id}`, `/pacientes/{id}/expediente`, `/imagenes/{id}` | número | UUID |
| Respuestas: `id_paciente`, `id_atencion`, `id_diagnostico_bucal`, `id_imagen` | número | UUID (texto) |
| Filtros: `GET /imagenes?id_paciente=...&id_atencion=...`, `GET /auditoria?id_paciente=...` | número | UUID |
| Subida de imagen (`FormData`): `id_paciente`, `id_atencion`, `id_diagnostico_bucal` | número | UUID |

Reglas para el front:
- Trata el UUID como **texto opaco**: no lo conviertas a número ni asumas orden entre ellos.
- Los nombres de los campos **no cambian**; solo cambia su valor.
- Para **mostrar** al usuario sigue usando `codigo` (p. ej. `P-007`) y los demás campos legibles. El `codigo` es solo para mostrar y buscar en el cuadro de texto: **no** sirve como identificador de ruta.
- Si el id no existe, la respuesta es 404; si no tiene forma de UUID, 422.

## 5. Atenciones y catálogos (Sprint 7)

Todas las rutas llevan `Authorization: Bearer <token>`. Leer: odontólogo o administrador. Crear/editar catálogos: solo administrador.

| Pantalla | Llamada |
|---|---|
| Atenciones (tabla) | `GET /api/v1/atenciones?q=&cod_4=&id_paciente=<uuid>&id_aseguradora=&fecha_desde=&fecha_hasta=&page=&page_size=` |
| Nueva atención (listas desplegables) | `GET /api/v1/aseguradoras` · `GET /api/v1/tratamientos` · `GET /api/v1/profesionales` · `GET /api/v1/profesionales/yo` |
| Guardar atención | `POST /api/v1/atenciones` (JSON de abajo) → 201 con el detalle |
| Detalle de atención | `GET /api/v1/atenciones/{id_atencion}` (UUID) |
| Administrar catálogos (admin) | `POST` y `PATCH /{id}` en `/aseguradoras`, `/tratamientos`, `/profesionales`; inactivar = `PATCH {"activo": false}` |

```json
{
  "id_paciente": "<uuid del paciente>",
  "fecha_atencion": "2026-10-01",
  "hora_atencion": "10:30:00",
  "id_aseguradora": 1,
  "ubicacion": "Piso 3",
  "id_profesional": null,
  "profesional_texto": null,
  "plan_tratamiento": "Operatoria y RX",
  "observaciones": null,
  "ids_tratamientos": [1, 2],
  "diagnostico_hospitalario": { "descripcion_original": "Tumor de colon", "cod_4": "C187" },
  "diagnosticos_bucales": [ { "descripcion": "Caries de la dentina", "codigos": ["K021"] } ]
}
```

- Los códigos CIE-10 aceptan con o sin punto (`K02.1` o `K021`).
- Cada diagnóstico bucal necesita **al menos un código odontológico**; el de hospitalización puede ser cualquier código (o ir solo con texto).
- Si no se envía `id_profesional` ni `profesional_texto`, se usa el profesional enlazado al usuario que inicia sesión (`profesional.auth_id` = su id en Supabase Auth).
- La fecha no puede ser futura. Errores: 404 paciente inexistente, 422 catálogo inexistente/inactivo o código no válido.
- Las imágenes de la atención se suben después con `POST /api/v1/imagenes` enviando `id_atencion` (y opcionalmente `id_diagnostico_bucal`).
- El expediente y el detalle ahora incluyen `codigo_atencion` (ej. `A007`, solo para mostrar) y `tratamientos`.

## 6. Importar datos e imágenes en lote (Sprint 8)

Pantalla "Importar datos". **Solo rol `administrador`** (con el rol odontólogo responde 403). Los archivos se envían como `multipart/form-data`, campo `archivo`; **no** pongas `Content-Type` a mano (el navegador agrega el límite del formulario).

| Acción | Llamada |
|---|---|
| Cargar el catálogo CIE-10 (**una sola vez**) | `POST /api/v1/importaciones/catalogo-cie10` — Excel original `.xls`/`.xlsx`; los odontológicos se leen del resaltado o subrayado de las celdas. Con el catálogo ya cargado responde **409**. |
| Importar atenciones y pacientes | `POST /api/v1/importaciones/atenciones` — Excel o CSV. Necesita el catálogo cargado. Repetir el archivo no duplica nada. |
| Historial | `GET /api/v1/importaciones` · `GET /api/v1/importaciones/{id}` |
| Cola de revisión (filas que no se pudieron cargar) | `GET /api/v1/importaciones/{id}/filas?estado=revision` |
| Marcar una fila como resuelta | `PATCH /api/v1/importaciones/{id}/filas/{id_fila}` con `{"estado":"resuelta"}` |
| Subir varias imágenes de un paciente | `POST /api/v1/imagenes/lote` — campos `id_paciente` (UUID), `archivos` (repetido, hasta 50) y opcional `id_atencion` |

```js
const form = new FormData();
form.append("archivo", fileInput.files[0]);          // File del <input type="file">
const r = await fetch(`${API}/api/v1/importaciones/catalogo-cie10`, {
  method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
});
```

La respuesta de una importación trae `total`, `insertados`, `omitidos`, `rechazados`, `odontologicos` (catálogo), `pacientes_nuevos`, `bucales_sin_codigo` y `ejemplos` (primeros motivos de revisión). Errores: 413 archivo muy grande (máx. 25 MB), 415 no es Excel/CSV, 422 estructura inesperada. La carga del catálogo puede tardar unos segundos: muestra un indicador de espera.

En el lote de imágenes la respuesta es 200 aunque falle alguna: cada elemento de `resultados` trae `imagen` o `error` (duplicada, formato no permitido…).

## 7. Reportes e Inicio (Sprint 9)

Rol odontólogo o administrador. Todos los filtros son opcionales y van en la URL.

| Pantalla | Llamada |
|---|---|
| Inicio (KPIs, gráficos, últimas atenciones) | `GET /api/v1/inicio/resumen` |
| Lista "Tipo de reporte" | `GET /api/v1/reportes/tipos` → `[{tipo, titulo}]` (8 tipos) |
| Vista previa / "Generar reporte" | `GET /api/v1/reportes/{tipo}?fecha_desde=2026-09-01&fecha_hasta=2026-09-30&id_aseguradora=&cod_4=&id_profesional=` |
| "Exportar Excel" | `GET /api/v1/reportes/{tipo}/excel` (mismos filtros): devuelve el `.xlsx` |
| "Exportar PDF" / "Descargar PDF" | **Lo genera el front** con la respuesta de la vista previa (impresión del navegador o jsPDF). El backend no genera PDF. |

Valores de `{tipo}`: `total_atenciones`, `atenciones_por_aseguradora`, `atenciones_por_diagnostico_hospitalario`, `distribucion_diagnosticos_bucales`, `tratamientos_registrados`, `atenciones_por_profesional`, `registros_por_fecha`, `relacion_hospitalario_bucal`.

La respuesta del reporte trae `titulo`, `generado_en`, `totales` {pacientes, atenciones, imagenes}, `filas` [{etiqueta, etiqueta_secundaria, cantidad, porcentaje}], `columna_principal`/`columna_secundaria` (encabezados de la tabla), `hallazgo` (frase destacada) y `truncado` (máx. 200 filas). Errores: 404 tipo inexistente, 422 fecha inicial posterior a la final.

Para descargar el Excel con el token usa `fetch` + `blob` (un enlace directo no envía el encabezado `Authorization`):
```js
const r = await fetch(`${API}/api/v1/reportes/${tipo}/excel?${params}`, { headers: { Authorization: `Bearer ${token}` } });
const url = URL.createObjectURL(await r.blob());
Object.assign(document.createElement("a"), { href: url, download: `reporte_${tipo}.xlsx` }).click();
```

## 8. Cosas que suelen fallar

| Síntoma en el navegador | Causa | Solución |
|---|---|---|
| `blocked by CORS policy: No 'Access-Control-Allow-Origin'` | el dominio no está en `CORS_ORIGINS`, tiene barra final o falta `https://`; o la API aún no redespliegó | corregir la variable y redesplegar; revisar que sea idéntico a la barra del navegador |
| El mismo error pero solo en la primera petición del día | el plan gratuito de Render duerme el servicio (~1 min al despertar) | reintentar; en el front mostrar "Conectando…" y llamar a `GET /health` al cargar |
| 401 | token vencido (1 h) o `AUTH_ISSUER`/`AUTH_AUDIENCE`/`AUTH_JWKS_URL` mal escritos | volver a iniciar sesión; revisar variables |
| 403 "Rol insuficiente" | el usuario no tiene `app_metadata.roles` | paso 4 de la sección 2 y volver a entrar |
| Subida de imagen da 422 | falta `archivo` o `id_paciente`, el `id_paciente` no es un UUID, o se puso `Content-Type` a mano | usar el UUID que devolvió la API y `FormData` sin cabecera `Content-Type` |
| 422 al abrir una ficha o un expediente | se está usando un número o el `codigo` (`P-007`) en la ruta | usar `id_paciente` (UUID) de la respuesta del listado |
| La imagen no carga | el enlace caducó (5 min) | volver a pedir el listado |

## 9. Orden recomendado para integrar

1. Conectar login, listar pacientes, crear paciente y subir imagen.
2. Cuando el front esté desplegado: agregar su dirección `https://...` a `CORS_ORIGINS`.
3. Al pasar a producción: `CORS_ORIGINS` solo con `https://`, `DOCS_ENABLED=false`, `ENVIRONMENT=production`.
