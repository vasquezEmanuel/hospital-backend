"""v1.2 — lo que el front pide y el esquema no tenía.

- aseguradora.activo: botón "Aseguradoras" (administración del catálogo).
- tratamiento, atencion_x_tratamiento: "Operatoria · RX · CP · DTT" y reporte "Tratamientos registrados".
- importacion, importacion_fila: pantalla "Importar datos" y cola de revisión manual del ETL.

Solo agrega columnas con DEFAULT y tablas nuevas: compatible hacia atrás.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE aseguradora ADD COLUMN activo BOOLEAN NOT NULL DEFAULT TRUE""")
    op.execute(
        """CREATE TABLE tratamiento (
    id_tratamiento  SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE
)"""
    )
    op.execute(
        """CREATE TABLE atencion_x_tratamiento (
    id_atencion     INTEGER NOT NULL REFERENCES atencion (id_atencion),
    id_tratamiento  INTEGER NOT NULL REFERENCES tratamiento (id_tratamiento),
    PRIMARY KEY (id_atencion, id_tratamiento)
)"""
    )
    op.execute("""CREATE INDEX idx_atencion_x_tratamiento_trat ON atencion_x_tratamiento (id_tratamiento)""")
    op.execute(
        """CREATE TABLE importacion (
    id_importacion   SERIAL PRIMARY KEY,
    id_profesional   INTEGER REFERENCES profesional (id_profesional),
    tipo             VARCHAR(20) NOT NULL CHECK (tipo IN ('atenciones', 'cie10', 'imagenes')),
    nombre_archivo   VARCHAR(255) NOT NULL,
    estado           VARCHAR(20) NOT NULL DEFAULT 'cargado'
                     CHECK (estado IN ('cargado', 'validado', 'procesando', 'completado', 'fallido')),
    total_registros  INTEGER NOT NULL DEFAULT 0,   
    insertados       INTEGER NOT NULL DEFAULT 0,
    actualizados     INTEGER NOT NULL DEFAULT 0,
    rechazados       INTEGER NOT NULL DEFAULT 0,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_en    TIMESTAMPTZ
)"""
    )
    op.execute("""CREATE INDEX idx_importacion_fecha ON importacion (creado_en)""")
    op.execute(
        """CREATE TABLE importacion_fila (
    id_fila          BIGSERIAL PRIMARY KEY,
    id_importacion   INTEGER NOT NULL REFERENCES importacion (id_importacion),
    numero_fila      INTEGER NOT NULL,
    estado           VARCHAR(15) NOT NULL DEFAULT 'revision'
                     CHECK (estado IN ('revision', 'rechazada', 'resuelta')),
    motivo           TEXT NOT NULL,        
    datos            JSONB NOT NULL,       
    resuelto_por     INTEGER REFERENCES profesional (id_profesional),
    resuelto_en      TIMESTAMPTZ
)"""
    )
    op.execute("""CREATE INDEX idx_importacion_fila_imp ON importacion (id_importacion)""")
    op.execute("""CREATE INDEX idx_importacion_fila_estado ON importacion (estado)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS importacion_fila, importacion, atencion_x_tratamiento, tratamiento CASCADE")
    op.execute("ALTER TABLE aseguradora DROP COLUMN activo")
