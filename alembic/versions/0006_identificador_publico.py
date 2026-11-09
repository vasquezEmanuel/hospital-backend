"""v1.5 — identificador público UUID para lo que la API expone.

Por qué cambia el esquema: los identificadores SERIAL (1, 2, 3...) delatan cuántos pacientes hay, permiten recorrer
la API probando números y no sirven de referencia estable si algún día se combinan bases. Se añade `public_id` (UUID
aleatorio) a paciente, atencion, diagnostico_bucal e imagen_clinica: es lo único que la API entrega y recibe. El SERIAL
se conserva como clave interna (relaciones, ETL, auditoría), por eso no se toca ninguna llave foránea.

Las filas existentes reciben su UUID al crear la columna: el valor por defecto es volátil, así que PostgreSQL lo
evalúa fila por fila. No se pierde ni se modifica ningún dato.
Bajar de versión (downgrade) elimina las columnas: los UUID entregados dejarían de existir.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLAS = ("paciente", "atencion", "diagnostico_bucal", "imagen_clinica")


def upgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"ALTER TABLE {tabla} ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE")


def downgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"ALTER TABLE {tabla} DROP COLUMN public_id")
