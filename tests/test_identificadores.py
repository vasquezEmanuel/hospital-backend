"""Sprint 6 (esquema v1.5): la API solo expone identificadores públicos UUID; la clave entera es interna.

Corresponde a la seguridad de datos de pacientes (no enumerar pacientes, imágenes ni atenciones recorriendo números).
"""

import importlib.util
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.main import app
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento
from functions.indexar_imagen.nucleo import indexar_clave

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
NUEVO = {"tipo_documento": "CC", "documento_identidad": "52880143", "nombre": "Ana Martínez"}
INEXISTENTE = "00000000-0000-4000-8000-000000000000"
TABLAS = ("paciente", "atencion", "diagnostico_bucal", "imagen_clinica")


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a
    return a


def test_las_cuatro_tablas_tienen_public_id_uuid_obligatorio_y_unico(db):
    for tabla in TABLAS:
        col = db.execute(
            text(
                "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'public_id'"
            ),
            {"t": tabla},
        ).one()
        assert col.data_type == "uuid" and col.is_nullable == "NO" and "gen_random_uuid" in col.column_default
        unico = db.execute(
            text("SELECT count(*) FROM pg_indexes WHERE tablename = :t AND indexdef LIKE '%UNIQUE%(public_id)%'"),
            {"t": tabla},
        ).scalar_one()
        assert unico == 1


def test_la_migracion_da_un_uuid_distinto_a_cada_fila_existente(db):
    """Se ejecuta el SQL real de la migración 0006 sobre una tabla que ya tiene filas."""
    ruta = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0006_identificador_publico.py"
    spec = importlib.util.spec_from_file_location("migracion_0006", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    db.execute(text("CREATE TEMP TABLE t_previa (id SERIAL PRIMARY KEY, dato TEXT)"))
    db.execute(text("INSERT INTO t_previa (dato) VALUES ('a'), ('b'), ('c')"))
    with (
        patch.object(migracion, "TABLAS", ("t_previa",)),
        patch.object(migracion.op, "execute", side_effect=lambda sql: db.execute(text(sql))),
    ):
        migracion.upgrade()
        ids = db.execute(text("SELECT public_id FROM t_previa")).scalars().all()
        assert len(ids) == 3 and len(set(ids)) == 3 and all(isinstance(i, uuid.UUID) for i in ids)
        assert (
            db.execute(text("SELECT count(*) FROM t_previa WHERE dato IS NOT NULL")).scalar_one() == 3
        )  # datos intactos
        migracion.downgrade()
    assert not db.execute(
        text("SELECT 1 FROM information_schema.columns WHERE table_name = 't_previa' AND column_name = 'public_id'")
    ).first()


def test_la_api_entrega_uuid_y_nunca_la_clave_interna(client, seed, db, almacen):
    creado = client.post("/api/v1/pacientes", json=NUEVO).json()
    interno = db.execute(text("SELECT id_paciente FROM paciente WHERE documento_identidad = '52880143'")).scalar_one()
    assert uuid.UUID(creado["id_paciente"]).version == 4 and creado["id_paciente"] != str(interno)
    assert client.get(f"/api/v1/pacientes/{creado['id_paciente']}").status_code == 200
    subida = client.post(
        "/api/v1/imagenes",
        data={"id_paciente": creado["id_paciente"]},
        files={"archivo": ("a.jpg", JPEG, "image/jpeg")},
    ).json()
    assert uuid.UUID(subida["id_imagen"]) and subida["id_paciente"] == creado["id_paciente"]
    expediente = client.get(f"/api/v1/pacientes/{creado['id_paciente']}/expediente").json()
    assert expediente["imagenes_sin_atencion"][0]["id_imagen"] == subida["id_imagen"]
    maria = client.get(f"/api/v1/pacientes/{seed['maria'].public_id}/expediente").json()
    for atencion in maria["atenciones"]:
        assert uuid.UUID(atencion["id_atencion"])  # ni siquiera las atenciones de datos históricos llevan números


@pytest.mark.parametrize(
    "ruta",
    ["/api/v1/pacientes/1", "/api/v1/pacientes/1/expediente", "/api/v1/imagenes/1", "/api/v1/imagenes?id_paciente=1"],
)
def test_un_identificador_numerico_ya_no_sirve(client, seed, almacen, ruta):
    assert client.get(ruta).status_code == 422


def test_la_clave_del_almacenamiento_lleva_el_uuid_del_paciente(client, seed, db, almacen):
    client.post(
        "/api/v1/imagenes",
        data={"id_paciente": str(seed["maria"].public_id)},
        files={"archivo": ("a.jpg", JPEG, "image/jpeg")},
    )
    clave = db.execute(text("SELECT url_almacenamiento FROM imagen_clinica")).scalar_one()
    assert clave.startswith(f"pacientes/{seed['maria'].public_id}/")  # la URL firmada contiene la clave


def test_el_indexador_reconoce_carpetas_con_uuid_y_las_antiguas_numericas(db, seed):
    maria = seed["maria"]
    nueva = indexar_clave(db, f"pacientes/{maria.public_id}/a.jpg", 10)
    antigua = indexar_clave(db, f"pacientes/{maria.id_paciente}/b.jpg", 10)
    assert nueva.estado == "registrada" and antigua.estado == "registrada"
    assert indexar_clave(db, f"pacientes/{INEXISTENTE}/c.jpg", 10).estado == "sin_paciente"
    ids = db.execute(text("SELECT DISTINCT id_paciente FROM imagen_clinica")).scalars().all()
    assert ids == [maria.id_paciente]


def test_consultar_un_uuid_inexistente_da_404_y_queda_en_auditoria(client, seed, db):
    assert client.get(f"/api/v1/pacientes/{INEXISTENTE}").status_code == 404
    fila = db.execute(text("SELECT accion, id_paciente, detalle FROM auditoria")).one()
    assert fila.accion == "consultar_paciente" and fila.id_paciente is None
    assert fila.detalle == {"paciente_no_encontrado": INEXISTENTE}  # el intento no queda sin rastro
