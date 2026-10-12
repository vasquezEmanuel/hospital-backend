# Contraste: pantallas del front vs. `schema.sql`

Fuente: 14 PDFs del equipo de front (Login, Inicio, Pacientes, Pacientes_2, Pacientes_Registro, Atenciones,
Detalle_Atencion, Workspace/Nueva Atención, Diagnósticos, Imágenes, Importar, Reportes, Reporte, Sidebar).

## A. Cambios al esquema (aplicados en v1.1 → `alembic/versions/0002_ajustes_front.py`)

| # | Pantalla | Qué muestra/pide el front | Estado en v1.0 | Cambio |
|---|----------|---------------------------|----------------|--------|
| 1 | Nuevo paciente | Campo **Tipo documento** | No existía | `paciente.tipo_documento` (CC, TI, RC, CE, PA, PE, PT), NULL en históricos |
| 2 | Ficha del paciente | "42 años · Femenino · SURA · **Bogotá D.C.**" | Sin ciudad | `paciente.ciudad` |
| 3 | Detalle de atención | "12 sep 2026 · **09:30**" | Solo `DATE` | `atencion.hora_atencion TIME` (NULL en históricos: la fuente solo trae fecha) |
| 4 | Detalle de atención | "**Registrada el** 12 de septiembre" | Sin fecha de registro | `atencion.creado_en` (+ `paciente.creado_en`) |

## A2. Cambios v1.2 (`alembic/versions/0003_importador_y_tratamientos.py`)

| # | Pantalla | Qué pide el front | Cambio |
|---|----------|-------------------|--------|
| 5 | Detalle de atención / Reportes | "Operatoria · RX · CP · DTT" y reporte "Tratamientos registrados" | `tratamiento` (catálogo) + `atencion_x_tratamiento` (N:M). `plan_tratamiento` se conserva como texto original. Catálogo vacío: validar valores con la Dra. Alvarez |
| 6 | Importar datos | "120 registros encontrados", "Procesar información" y la cola de revisión manual prometida en el documento técnico | `importacion` (estado y conteos) + `importacion_fila` (filas rechazadas o en revisión con el JSON original) |
| 7 | Atenciones → botón "Aseguradoras" | Administración del catálogo | `aseguradora.activo` (se inactiva, no se borra) |

Lo que **no** requirió cambio: Reportes (8 tipos) e Inicio (KPIs) se calculan con consultas sobre las tablas existentes.
Sigue pendiente la decisión sobre el CSV del catálogo CIE-10 (punto C.2): el esquema no cambia, pero el importador necesita saber de dónde sale `es_odontologico`.

## B. Datos que el front muestra y que se DERIVAN (no se agregan columnas)

| Dato del front | Cómo se obtiene |
|---|---|
| ID de paciente `P-001` | `P-{id_paciente:03d}` calculado en la API (también se puede buscar por él) |
| Código de atención `AT-2026-0912` / `A001` | Se calcula desde `id_atencion` (Sprint 3). **El front muestra "A001" repetido en todas las filas: es maqueta, debe ser único.** |
| Edad | Desde `fecha_nacimiento` |
| Aseguradora del paciente | Aseguradora de su última atención (el paciente no tiene aseguradora fija) |
| Total de atenciones / Última atención | Agregados sobre `atencion` |
| Diagnósticos hospitalarios / bucales / imágenes del paciente | Conteos en el expediente (Sprint 3) |

## C. Contradicciones entre el front y el Documento Técnico (requieren decisión del equipo / Dra. Alvarez)

1. **Diagnósticos → "Pacientes relacionados" busca por `C187` (tumor de colon, NO odontológico).**
   El documento define `GET /enfermedades/{cod_4}/pacientes` solo para códigos en *diagnóstico bucal*.
   El front espera buscar también por código de *hospitalización*. Propuesta: parámetro `origen=bucal|hospitalario|todos` (Sprint 4).
2. **Importar acepta el catálogo CIE-10 en CSV, pero el documento deriva `es_odontologico` del subrayado del Excel.**
   Un CSV pierde el formato → ningún código quedaría marcado odontológico. Opciones: (a) catálogo solo XLSX;
   (b) CSV con columna `es_odontologico` explícita; (c) la odontóloga marca los códigos desde la UI.
3. **Importar es una pantalla dentro de la app** (subir → "120 registros encontrados" → "Procesar información"),
   pero el documento define el ETL como *job serverless* y la migración como responsabilidad del hospital.
   Esto implica endpoints `/importaciones` (subir, previsualizar, procesar, estado) **y una tabla para la cola de revisión
   manual** que el documento promete y el esquema no tiene. Decidir antes del Sprint 2.
4. **Reportes (8 tipos, exportar PDF/Excel) e Inicio (KPIs y gráficos) no están en el documento ni en los sprints.**
   Hay que planificarlos (propuesta: Sprint 4, tras tener atenciones y diagnósticos).
5. **Nueva atención permite un solo "Diagnóstico bucal"**; la regla de negocio es 0..N. El front debe permitir selección múltiple
   y, por cada diagnóstico bucal, 1..N códigos CIE-10 odontológicos.
6. **Imágenes**: el front asocia imagen → paciente + diagnóstico. Las migradas no tienen diagnóstico ni atención
   (regla 4): mostrar "Sin asociar". La subida desde Nueva Atención debe permitir elegir el diagnóstico de cada imagen.
7. **Login** pide "Usuario"; `profesional` no tiene username. Lo resuelve el IdP (usuario/correo). El pie dice
   "Prototipo académico": no corresponde a un servicio en producción.
8. **Botón "Aseguradoras"** (Atenciones) implica CRUD del catálogo (solo administrador): se agrega a Sprint 3 junto a atenciones.

## D. Errores de maqueta para el front (no afectan la BD)
- Nueva Atención: el desplegable "Profesional" tiene placeholder "Género".
- Fechas `DD/MM/AA` (año de 2 dígitos): usar `DD/MM/AAAA`.
- Pacientes: "Mostrando 1–5 de 24" vs. "1.248 pacientes registrados".
- Acentos faltantes ("Atencion", "Diagnostico", "Imagenes").
