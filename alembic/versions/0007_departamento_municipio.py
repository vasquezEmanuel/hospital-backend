"""v1.6 — ubicación del paciente por departamento y municipio (catálogo DIVIPOLA del DANE).

Por qué cambia el esquema: el formulario de paciente pide departamento y ciudad. Con un texto libre (`ciudad`) cada
digitador escribe distinto ("Bogotá", "BOGOTA D.C.", "bogota"), no se puede filtrar ni agrupar por región y no hay forma
de validar. Se agregan dos catálogos con los códigos oficiales del DANE (`departamento`: 2 dígitos; `municipio`:
5 dígitos, los dos primeros son el departamento) y `paciente.codigo_municipio`, de donde se deduce el departamento.

`paciente.ciudad` se conserva: guarda el nombre del municipio cuando se elige uno del catálogo y sirve como texto libre
para quien vive fuera de Colombia o en un lugar que no está en el catálogo. Las filas existentes no se modifican.
Bajar de versión elimina las dos tablas y la columna nueva.

Revision ID: 0007
Revises: 0006
"""

import csv
from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_DATOS = Path(__file__).resolve().parent.parent / "data"


def _filas(nombre: str) -> list[dict[str, str]]:
    with open(_DATOS / nombre, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE departamento (
            codigo  CHAR(2) PRIMARY KEY,
            nombre  VARCHAR(100) NOT NULL UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE municipio (
            codigo               CHAR(5) PRIMARY KEY,
            nombre               VARCHAR(100) NOT NULL,
            codigo_departamento  CHAR(2) NOT NULL REFERENCES departamento (codigo),
            CONSTRAINT ck_municipio_departamento CHECK (substr(codigo, 1, 2) = codigo_departamento)
        )
        """
    )
    op.execute("CREATE INDEX idx_municipio_departamento ON municipio (codigo_departamento)")
    op.execute("ALTER TABLE paciente ADD COLUMN codigo_municipio CHAR(5) REFERENCES municipio (codigo)")
    op.execute("CREATE INDEX idx_paciente_municipio ON paciente (codigo_municipio)")

    conexion = op.get_bind()
    conexion.exec_driver_sql(
        "INSERT INTO departamento (codigo, nombre) VALUES (%(codigo)s, %(nombre)s)",
        _filas("divipola_departamentos.csv"),
    )
    conexion.exec_driver_sql(
        "INSERT INTO municipio (codigo, nombre, codigo_departamento) "
        "VALUES (%(codigo)s, %(nombre)s, %(codigo_departamento)s)",
        _filas("divipola_municipios.csv"),
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_paciente_municipio")
    op.execute("ALTER TABLE paciente DROP COLUMN codigo_municipio")
    op.execute("DROP TABLE municipio")
    op.execute("DROP TABLE departamento")
