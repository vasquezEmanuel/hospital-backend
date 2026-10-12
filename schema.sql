-- ============================================================================
-- Esquema v1.2 — Sistema de Gestión de Pacientes, Enfermedades e
-- Imágenes Clínicas — Hospital Alma Mater, Área de Odontología.
-- Motor: PostgreSQL 16
-- v1.1: ajustes tras contrastar el front (ver alembic/versions/0002_ajustes_front.py).
-- v1.2: tratamientos, cola de revisión del importador, aseguradora.activo (ver alembic/versions/0003_*.py).
--       La línea base v1.0 vive intacta en alembic/sql/0001_baseline.sql.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Catálogos
-- ---------------------------------------------------------------------------
-- Nota: sexo y rol NO se modelan como tablas. Sexo tiene 2-3 valores fijos sin
-- atributos propios (una tabla no aporta nada sobre un CHECK). Rol se gestiona
-- como grupos/claims en el proveedor de identidad gestionado (Cognito/Auth0),
-- que ya es la fuente de verdad de autenticación — duplicarlo en la BD
-- arriesgaría desincronización. aseguradora sí se mantiene como tabla: crece,
-- la administra un usuario y normalizarla evita inconsistencias de escritura.

CREATE TABLE aseguradora (
    id_aseguradora  SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL UNIQUE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE   -- v1.2: botón "Aseguradoras" (admin); se inactiva, no se borra
);

-- cod_4 es la clave de toda relación con CIE-10 (decisión vigente).
-- cod_3/descripcion_3 se conservan como columnas informativas, sin tabla aparte.
CREATE TABLE cie10 (
    cod_4               VARCHAR(10) PRIMARY KEY,
    cod_3               VARCHAR(5),
    descripcion_3       TEXT,
    descripcion_4       TEXT NOT NULL,
    es_odontologico     BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_cie10_odontologico ON cie10 (es_odontologico);

-- ---------------------------------------------------------------------------
-- Identidad y acceso
-- ---------------------------------------------------------------------------

CREATE TABLE profesional (
    id_profesional  SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    identificacion  VARCHAR(20) NOT NULL UNIQUE,
    correo          VARCHAR(150) NOT NULL UNIQUE,
    especializacion VARCHAR(150),
    auth_id         VARCHAR(255) UNIQUE,  -- id del usuario en el IdP; sus roles/grupos viajan en el token JWT, no se duplican aquí
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- Núcleo clínico
-- ---------------------------------------------------------------------------

CREATE TABLE paciente (
    id_paciente         SERIAL PRIMARY KEY,
    tipo_documento      VARCHAR(3) CHECK (tipo_documento IN ('CC', 'TI', 'RC', 'CE', 'PA', 'PE', 'PT')),  -- v1.1: formulario "Nuevo paciente"; NULL en datos históricos
    documento_identidad VARCHAR(20) NOT NULL UNIQUE,
    nombre              VARCHAR(150) NOT NULL,
    fecha_nacimiento    DATE,                       -- no existe en la fuente actual
    sexo                CHAR(1) CHECK (sexo IN ('M', 'F', 'O')),  -- no existe en la fuente actual
    telefono            VARCHAR(20),                -- no existe en la fuente actual
    correo              VARCHAR(150),               -- no existe en la fuente actual
    ciudad              VARCHAR(100),               -- v1.1: la ficha del paciente muestra la ciudad
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()  -- v1.1
);

CREATE TABLE atencion (
    id_atencion         SERIAL PRIMARY KEY,
    id_paciente         INTEGER NOT NULL REFERENCES paciente (id_paciente),
    fecha_atencion      DATE NOT NULL,
    hora_atencion       TIME,           -- v1.1: el detalle de atención muestra la hora; NULL en históricos (la fuente solo trae fecha)
    id_aseguradora      INTEGER REFERENCES aseguradora (id_aseguradora),
    ubicacion           VARCHAR(150),
    id_profesional      INTEGER REFERENCES profesional (id_profesional),
    profesional_texto   VARCHAR(150),   -- respaldo si el profesional histórico no coincide con uno registrado
    plan_tratamiento    TEXT,
    observaciones       TEXT,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()  -- v1.1: "Registrada el ..." del detalle de atención
);
CREATE INDEX idx_atencion_paciente ON atencion (id_paciente);
CREATE INDEX idx_atencion_fecha ON atencion (fecha_atencion);

-- Diagnóstico de hospitalización: a lo sumo 1 por atención, relación simple con CIE-10.
CREATE TABLE diagnostico_hospitalario (
    id_diagnostico_hosp SERIAL PRIMARY KEY,
    id_atencion         INTEGER NOT NULL UNIQUE REFERENCES atencion (id_atencion),
    descripcion_original TEXT NOT NULL,   -- texto tal como viene de la fuente
    cod_4               VARCHAR(10) REFERENCES cie10 (cod_4),
    activo              BOOLEAN NOT NULL DEFAULT TRUE
);

-- Diagnóstico bucal: 0..N por atención (una fila por cada DIAGNÓSTICO BUCAL no vacío de la fuente).
CREATE TABLE diagnostico_bucal (
    id_diagnostico_bucal SERIAL PRIMARY KEY,
    id_atencion          INTEGER NOT NULL REFERENCES atencion (id_atencion),
    descripcion          TEXT NOT NULL,  -- texto tal como viene de la fuente
    activo                BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_diagnostico_bucal_atencion ON diagnostico_bucal (id_atencion);

-- Tabla puente N:M: cada diagnóstico bucal puede vincularse a 1 o más códigos CIE-10
-- (y un código puede repetirse en muchos diagnósticos). Este es el elemento central
-- de valor identificado en la propuesta de front.
CREATE TABLE cie10_x_diagnostico_bucal (
    cod_4                   VARCHAR(10) NOT NULL REFERENCES cie10 (cod_4),
    id_diagnostico_bucal    INTEGER NOT NULL REFERENCES diagnostico_bucal (id_diagnostico_bucal),
    PRIMARY KEY (cod_4, id_diagnostico_bucal)
);
CREATE INDEX idx_cie10xdx_cod4 ON cie10_x_diagnostico_bucal (cod_4);

-- Restricción de negocio: todo código vinculado como diagnóstico bucal debe ser odontológico.
CREATE OR REPLACE FUNCTION fn_validar_cie10_odontologico()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM cie10 WHERE cod_4 = NEW.cod_4 AND es_odontologico = TRUE
    ) THEN
        RAISE EXCEPTION 'El código CIE-10 % no está marcado como odontológico', NEW.cod_4;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_cie10_odontologico
BEFORE INSERT OR UPDATE ON cie10_x_diagnostico_bucal
FOR EACH ROW EXECUTE FUNCTION fn_validar_cie10_odontologico();

-- ---------------------------------------------------------------------------
-- Tratamientos (v1.2) — Detalle de atención ("Operatoria · RX · CP · DTT") y reporte "Tratamientos registrados".
-- Catálogo administrable + N:M con atencion. plan_tratamiento (texto libre) se conserva: es el dato de la fuente.
-- Vacío en históricos; los valores del catálogo se validan con la Dra. Alvarez.
-- ---------------------------------------------------------------------------

CREATE TABLE tratamiento (
    id_tratamiento  SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE atencion_x_tratamiento (
    id_atencion     INTEGER NOT NULL REFERENCES atencion (id_atencion),
    id_tratamiento  INTEGER NOT NULL REFERENCES tratamiento (id_tratamiento),
    PRIMARY KEY (id_atencion, id_tratamiento)
);
CREATE INDEX idx_atencion_x_tratamiento_trat ON atencion_x_tratamiento (id_tratamiento);

-- ---------------------------------------------------------------------------
-- Importador (v1.2) — pantalla "Importar datos" y cola de revisión manual (Fase 3 del documento técnico).
-- Los casos sin coincidencia NO se descartan ni se asignan sin respaldo: quedan en importacion_fila.
-- ---------------------------------------------------------------------------

CREATE TABLE importacion (
    id_importacion   SERIAL PRIMARY KEY,
    id_profesional   INTEGER REFERENCES profesional (id_profesional),
    tipo             VARCHAR(20) NOT NULL CHECK (tipo IN ('atenciones', 'cie10', 'imagenes')),
    nombre_archivo   VARCHAR(255) NOT NULL,
    estado           VARCHAR(20) NOT NULL DEFAULT 'cargado'
                     CHECK (estado IN ('cargado', 'validado', 'procesando', 'completado', 'fallido')),
    total_registros  INTEGER NOT NULL DEFAULT 0,   -- "120 registros encontrados"
    insertados       INTEGER NOT NULL DEFAULT 0,
    actualizados     INTEGER NOT NULL DEFAULT 0,
    rechazados       INTEGER NOT NULL DEFAULT 0,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_en    TIMESTAMPTZ
);
CREATE INDEX idx_importacion_fecha ON importacion (creado_en);

CREATE TABLE importacion_fila (
    id_fila          BIGSERIAL PRIMARY KEY,
    id_importacion   INTEGER NOT NULL REFERENCES importacion (id_importacion),
    numero_fila      INTEGER NOT NULL,
    estado           VARCHAR(15) NOT NULL DEFAULT 'revision'
                     CHECK (estado IN ('revision', 'rechazada', 'resuelta')),
    motivo           TEXT NOT NULL,        -- p. ej. "diagnóstico sin coincidencia en el catálogo CIE-10"
    datos            JSONB NOT NULL,       -- fila original tal como vino de la fuente
    resuelto_por     INTEGER REFERENCES profesional (id_profesional),
    resuelto_en      TIMESTAMPTZ
);
CREATE INDEX idx_importacion_fila_imp ON importacion (id_importacion);
CREATE INDEX idx_importacion_fila_estado ON importacion (estado);

-- ---------------------------------------------------------------------------
-- Imágenes clínicas
-- ---------------------------------------------------------------------------

CREATE TABLE imagen_clinica (
    id_imagen            SERIAL PRIMARY KEY,
    id_paciente          INTEGER NOT NULL REFERENCES paciente (id_paciente),
    id_atencion          INTEGER REFERENCES atencion (id_atencion),
    id_diagnostico_bucal INTEGER REFERENCES diagnostico_bucal (id_diagnostico_bucal),
    nombre_archivo       VARCHAR(255) NOT NULL,
    url_almacenamiento   TEXT NOT NULL,          -- key/ruta en el almacenamiento de objetos
    fecha_carga          TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata             JSONB,                  -- dimensiones, dispositivo, etc.
    checksum             VARCHAR(64),            -- integridad del archivo
    activo               BOOLEAN NOT NULL DEFAULT TRUE   -- borrado lógico
);
CREATE INDEX idx_imagen_paciente ON imagen_clinica (id_paciente);
CREATE INDEX idx_imagen_atencion ON imagen_clinica (id_atencion);

-- ---------------------------------------------------------------------------
-- Auditoría (requisito de seguridad)
-- ---------------------------------------------------------------------------

CREATE TABLE auditoria (
    id_evento       BIGSERIAL PRIMARY KEY,
    id_profesional  INTEGER NOT NULL REFERENCES profesional (id_profesional),
    accion          VARCHAR(100) NOT NULL,
    entidad_afectada VARCHAR(100),
    fecha_hora      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_origen       VARCHAR(45)
);
CREATE INDEX idx_auditoria_profesional ON auditoria (id_profesional);
CREATE INDEX idx_auditoria_fecha ON auditoria (fecha_hora);

COMMIT;
