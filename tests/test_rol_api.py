"""Sprint 5: el rol `hospital_api` (docs/sql/seguridad_bd.sql) tiene exactamente los permisos mínimos."""

from pathlib import Path

import psycopg.errors
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import get_settings

SQL = Path(__file__).resolve().parent.parent / "docs" / "sql" / "seguridad_bd.sql"
CLAVE = "clave_de_prueba_hospital_api_1"


@pytest.fixture(scope="module")
def motor_api(engine):
    """Aplica el script del repositorio sobre la base de pruebas y abre una conexión como hospital_api."""
    guion = SQL.read_text(encoding="utf-8")
    assert "CAMBIAR_ESTA_CONTRASENA" in guion
    with engine.begin() as c:  # el script se ejecuta dos veces: debe ser idempotente
        for _ in range(2):
            c.exec_driver_sql(guion.replace("%", "%%"))
        c.execute(text(f"ALTER ROLE hospital_api PASSWORD '{CLAVE}'"))
    url = make_url(get_settings().sqlalchemy_url).set(username="hospital_api", password=CLAVE)
    eng = create_engine(url, connect_args={"connect_timeout": 5})
    yield eng
    eng.dispose()


@pytest.fixture
def api(motor_api):
    """Conexión como la API; todo lo que haga se revierte."""
    with motor_api.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


def _falla_por_permisos(conn, sql):
    with pytest.raises((ProgrammingError, DBAPIError)) as e, conn.begin_nested():
        conn.execute(text(sql))
    assert isinstance(e.value.orig, psycopg.errors.InsufficientPrivilege)  # 42501: sin permiso (o bloqueado por RLS)


def test_la_api_puede_leer_crear_y_modificar_pacientes_e_imagenes(api):
    api.execute(text("SELECT count(*) FROM cie10")).scalar_one()
    id_ = api.execute(
        text(
            "INSERT INTO paciente (documento_identidad, nombre) VALUES ('9990001', 'Prueba Rol') RETURNING id_paciente"
        )
    ).scalar_one()
    api.execute(text("UPDATE paciente SET ciudad = 'Cali' WHERE id_paciente = :i"), {"i": id_})
    api.execute(
        text(
            "INSERT INTO imagen_clinica (id_paciente, nombre_archivo, url_almacenamiento) VALUES (:i, 'a.png', 'k/a')"
        ),
        {"i": id_},
    )
    api.execute(text("UPDATE imagen_clinica SET activo = FALSE WHERE id_paciente = :i"), {"i": id_})
    api.execute(text("INSERT INTO auditoria (accion, auth_sub) VALUES ('prueba', 'u1')"))
    assert api.execute(text("SELECT count(*) FROM auditoria")).scalar_one() >= 1


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM paciente",
        "TRUNCATE paciente CASCADE",
        "DELETE FROM imagen_clinica",
        "UPDATE auditoria SET accion = 'x'",
        "DELETE FROM auditoria",
        "TRUNCATE auditoria",
        "INSERT INTO cie10 (cod_4, descripcion_4) VALUES ('Z999', 'no debe')",
        "UPDATE cie10 SET descripcion_4 = 'no debe'",
        "INSERT INTO atencion (id_paciente, fecha_atencion) VALUES (1, now())",
        "SELECT * FROM alembic_version",
        "DROP TABLE paciente",
        "CREATE TABLE intruso (id int)",
        "ALTER TABLE paciente ADD COLUMN x int",
    ],
)
def test_la_api_no_puede_borrar_vaciar_ni_cambiar_el_esquema(api, sql):
    _falla_por_permisos(api, sql)
