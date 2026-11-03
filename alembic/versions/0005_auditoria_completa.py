"""v1.4 — auditoría completa e inmutable (regla 6: toda consulta o modificación de datos de un paciente se registra).

Por qué cambia el esquema: en v1.3 auditoria.id_profesional era obligatorio, pero los usuarios se autentican en el
proveedor de identidad y no necesariamente tienen una fila en `profesional` (roles y cuentas viven en el IdP). Ahora el
evento guarda siempre quién actuó (auth_sub) y, si existe, su fila de profesional. Se agregan el paciente afectado y un
detalle sin datos clínicos, y la tabla pasa a ser inmutable (triggers que impiden UPDATE, DELETE y TRUNCATE).

El cambio solo agrega columnas y restricciones: no toca eventos existentes.
Bajar de versión (downgrade) falla a propósito si ya hay eventos de usuarios sin fila de profesional:
no se borra auditoría.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE auditoria ALTER COLUMN id_profesional DROP NOT NULL")
    op.execute("ALTER TABLE auditoria ADD COLUMN auth_sub VARCHAR(255)")
    op.execute("ALTER TABLE auditoria ADD COLUMN email VARCHAR(150)")
    op.execute("ALTER TABLE auditoria ADD COLUMN id_paciente INTEGER")
    op.execute("ALTER TABLE auditoria ADD COLUMN detalle JSONB")
    op.execute(
        "ALTER TABLE auditoria ADD CONSTRAINT ck_auditoria_actor "
        "CHECK (id_profesional IS NOT NULL OR auth_sub IS NOT NULL)"
    )
    op.execute("CREATE INDEX idx_auditoria_paciente ON auditoria (id_paciente)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_auditoria_inmutable()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'La auditoria es inmutable: no se permite modificarla ni borrarla';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_auditoria_inmutable BEFORE UPDATE OR DELETE ON auditoria "
        "FOR EACH ROW EXECUTE FUNCTION fn_auditoria_inmutable()"
    )
    op.execute(
        "CREATE TRIGGER trg_auditoria_sin_truncate BEFORE TRUNCATE ON auditoria "
        "FOR EACH STATEMENT EXECUTE FUNCTION fn_auditoria_inmutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_auditoria_sin_truncate ON auditoria")
    op.execute("DROP TRIGGER trg_auditoria_inmutable ON auditoria")
    op.execute("DROP FUNCTION fn_auditoria_inmutable()")
    op.execute("DROP INDEX idx_auditoria_paciente")
    op.execute("ALTER TABLE auditoria DROP CONSTRAINT ck_auditoria_actor")
    op.execute("ALTER TABLE auditoria DROP COLUMN detalle")
    op.execute("ALTER TABLE auditoria DROP COLUMN id_paciente")
    op.execute("ALTER TABLE auditoria DROP COLUMN email")
    op.execute("ALTER TABLE auditoria DROP COLUMN auth_sub")
    op.execute("ALTER TABLE auditoria ALTER COLUMN id_profesional SET NOT NULL")
