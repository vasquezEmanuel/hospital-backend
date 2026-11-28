"""v1.7 — varios diagnósticos de hospitalización por atención, cada uno con uno o más códigos CIE-10.

Por qué cambia el esquema: la coordinación clínica necesita registrar más de un diagnóstico general (de hospitalización)
por atención, igual que el diagnóstico bucal. Hasta v1.6 era 1:1 con la atención (`UNIQUE (id_atencion)`) y 1:1 con
CIE-10 (`cod_4`). Ahora tiene la misma forma que el bucal: 0..N diagnósticos por atención, cada uno con 0..N códigos
mediante la tabla puente `cie10_x_diagnostico_hospitalario`. Cualquier código CIE-10 es válido (no se exige que sea
odontológico, a diferencia del bucal). Se añade `public_id` UUID, que es lo que expone la API.

Los datos existentes se conservan: cada `cod_4` actual pasa a la tabla puente y después se elimina la columna.
Bajar de versión copia a `cod_4` el primer código de cada diagnóstico y vuelve a exigir uno por atención, por lo que
falla si alguna atención ya tiene dos o más diagnósticos de hospitalización.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE diagnostico_hospitalario DROP CONSTRAINT diagnostico_hospitalario_id_atencion_key")
    op.execute(
        "ALTER TABLE diagnostico_hospitalario ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE"
    )
    op.execute("CREATE INDEX idx_diagnostico_hospitalario_atencion ON diagnostico_hospitalario (id_atencion)")
    op.execute(
        """
        CREATE TABLE cie10_x_diagnostico_hospitalario (
            cod_4                VARCHAR(10) NOT NULL REFERENCES cie10 (cod_4),
            id_diagnostico_hosp  INTEGER NOT NULL REFERENCES diagnostico_hospitalario (id_diagnostico_hosp),
            PRIMARY KEY (cod_4, id_diagnostico_hosp)
        )
        """
    )
    op.execute("CREATE INDEX idx_cie10xdxhosp_cod4 ON cie10_x_diagnostico_hospitalario (cod_4)")
    op.execute(
        "INSERT INTO cie10_x_diagnostico_hospitalario (cod_4, id_diagnostico_hosp) "
        "SELECT cod_4, id_diagnostico_hosp FROM diagnostico_hospitalario WHERE cod_4 IS NOT NULL"
    )
    op.execute("ALTER TABLE diagnostico_hospitalario DROP COLUMN cod_4")


def downgrade() -> None:
    op.execute("ALTER TABLE diagnostico_hospitalario ADD COLUMN cod_4 VARCHAR(10) REFERENCES cie10 (cod_4)")
    op.execute(
        """
        UPDATE diagnostico_hospitalario d SET cod_4 = (
            SELECT min(p.cod_4) FROM cie10_x_diagnostico_hospitalario p
            WHERE p.id_diagnostico_hosp = d.id_diagnostico_hosp
        )
        """
    )
    op.execute("DROP TABLE cie10_x_diagnostico_hospitalario")
    op.execute("DROP INDEX idx_diagnostico_hospitalario_atencion")
    op.execute("ALTER TABLE diagnostico_hospitalario DROP COLUMN public_id")
    op.execute(
        "ALTER TABLE diagnostico_hospitalario "
        "ADD CONSTRAINT diagnostico_hospitalario_id_atencion_key UNIQUE (id_atencion)"
    )
