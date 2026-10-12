"""Línea base v1.0 — esquema definitivo entregado (10 tablas, trigger CIE-10 odontológico).

Revision ID: 0001
Revises:
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parent.parent / "sql" / "0001_baseline.sql"


def upgrade() -> None:
    # Alembic ya abre la transacción: se retiran BEGIN/COMMIT del archivo original.
    sql = _SQL.read_text(encoding="utf-8")
    sql = sql.replace("\nBEGIN;\n", "\n").replace("\nCOMMIT;\n", "\n")
    # Se usa la conexión psycopg directa, sin parámetros: así '%' del RAISE EXCEPTION no se interpreta
    # como marcador y se permiten varias sentencias en una sola ejecución (misma transacción de Alembic).
    op.get_bind().connection.driver_connection.execute(sql)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS auditoria, imagen_clinica, cie10_x_diagnostico_bucal, "
        "diagnostico_bucal, diagnostico_hospitalario, atencion, paciente, profesional, "
        "cie10, aseguradora CASCADE"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_validar_cie10_odontologico() CASCADE")
