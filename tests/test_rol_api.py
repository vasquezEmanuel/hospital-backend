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


def test_la_api_puede_registrar_atenciones_y_administrar_catalogos(api):
    """Sprint 7: altas de atención (con diagnósticos y tratamientos) y alta/edición de catálogos."""
    pac = api.execute(
        text("INSERT INTO paciente (documento_identidad, nombre) VALUES ('9990002', 'Prueba S7') RETURNING id_paciente")
    ).scalar_one()
    aseg = api.execute(
        text("INSERT INTO aseguradora (nombre) VALUES ('Aseg Prueba') RETURNING id_aseguradora")
    ).scalar_one()
    trat = api.execute(
        text("INSERT INTO tratamiento (nombre) VALUES ('Trat Prueba') RETURNING id_tratamiento")
    ).scalar_one()
    api.execute(text("INSERT INTO profesional (nombre, identificacion, correo) VALUES ('Dr Prueba', '777', 'p@x.co')"))
    api.execute(text("UPDATE aseguradora SET activo = FALSE WHERE id_aseguradora = :i"), {"i": aseg})
    api.execute(text("UPDATE tratamiento SET nombre = 'Trat Editado' WHERE id_tratamiento = :i"), {"i": trat})
    api.execute(text("UPDATE profesional SET activo = FALSE WHERE identificacion = '777'"))
    atencion = api.execute(
        text("INSERT INTO atencion (id_paciente, fecha_atencion) VALUES (:p, now()) RETURNING id_atencion"), {"p": pac}
    ).scalar_one()
    api.execute(
        text("INSERT INTO diagnostico_hospitalario (id_atencion, descripcion_original) VALUES (:a, 'x')"),
        {"a": atencion},
    )
    api.execute(text("INSERT INTO diagnostico_bucal (id_atencion, descripcion) VALUES (:a, 'x')"), {"a": atencion})
    api.execute(
        text("INSERT INTO atencion_x_tratamiento (id_atencion, id_tratamiento) VALUES (:a, :t)"),
        {"a": atencion, "t": trat},
    )


def test_la_api_puede_importar_pero_el_catalogo_cie10_solo_se_inserta(api):
    """Sprint 8: el catálogo se carga por la API (INSERT) pero no se edita (UPDATE queda para el propietario)."""
    api.execute(text("INSERT INTO cie10 (cod_4, cod_3, descripcion_4) VALUES ('Z998', 'Z99', 'solo prueba')"))
    imp = api.execute(
        text("INSERT INTO importacion (tipo, nombre_archivo) VALUES ('cie10', 'x.xls') RETURNING id_importacion")
    ).scalar_one()
    api.execute(text("UPDATE importacion SET estado = 'completado' WHERE id_importacion = :i"), {"i": imp})
    api.execute(
        text("INSERT INTO importacion_fila (id_importacion, numero_fila, motivo, datos) VALUES (:i, 2, 'm', '{}')"),
        {"i": imp},
    )
    api.execute(text("UPDATE importacion_fila SET estado = 'resuelta' WHERE id_importacion = :i"), {"i": imp})


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM paciente",
        "TRUNCATE paciente CASCADE",
        "DELETE FROM imagen_clinica",
        "UPDATE auditoria SET accion = 'x'",
        "DELETE FROM auditoria",
        "TRUNCATE auditoria",
        "UPDATE cie10 SET descripcion_4 = 'no debe'",
        "DELETE FROM cie10",
        "DELETE FROM importacion",
        "DELETE FROM importacion_fila",
        "UPDATE atencion SET observaciones = 'no debe'",
        "DELETE FROM atencion",
        "DELETE FROM diagnostico_bucal",
        "UPDATE diagnostico_bucal SET descripcion = 'no debe'",
        "DELETE FROM aseguradora",
        "DELETE FROM profesional",
        "SELECT * FROM alembic_version",
        "DROP TABLE paciente",
        "CREATE TABLE intruso (id int)",
        "ALTER TABLE paciente ADD COLUMN x int",
    ],
)
def test_la_api_no_puede_borrar_vaciar_ni_cambiar_el_esquema(api, sql):
    _falla_por_permisos(api, sql)
