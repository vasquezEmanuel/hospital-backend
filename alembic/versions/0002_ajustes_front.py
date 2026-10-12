"""v1.1 — ajustes tras contrastar las pantallas del front con el esquema.

- paciente.tipo_documento  (formulario "Nuevo paciente": campo "Tipo documento")
- paciente.ciudad          (ficha del paciente: "42 años · Femenino · SURA · Bogotá D.C.")
- paciente.creado_en       (trazabilidad)
- atencion.hora_atencion   (detalle de atención: "12 sep 2026 · 09:30")
- atencion.creado_en       (detalle de atención: "Registrada el 12 de septiembre de 2026")

Todas las columnas son opcionales o con DEFAULT: la migración es compatible hacia atrás.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE paciente ADD COLUMN tipo_documento VARCHAR(3) "
        "CHECK (tipo_documento IN ('CC', 'TI', 'RC', 'CE', 'PA', 'PE', 'PT'))"
    )
    op.execute("ALTER TABLE paciente ADD COLUMN ciudad VARCHAR(100)")
    op.execute("ALTER TABLE paciente ADD COLUMN creado_en TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("ALTER TABLE atencion ADD COLUMN hora_atencion TIME")
    op.execute("ALTER TABLE atencion ADD COLUMN creado_en TIMESTAMPTZ NOT NULL DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE atencion DROP COLUMN creado_en, DROP COLUMN hora_atencion")
    op.execute("ALTER TABLE paciente DROP COLUMN creado_en, DROP COLUMN ciudad, DROP COLUMN tipo_documento")
