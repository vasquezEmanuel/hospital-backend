"""Esquema v1.2: tratamientos, cola de revisión del importador y aseguradora.activo."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Aseguradora, Atencion


def test_aseguradora_activa_por_defecto(db):
    a = Aseguradora(nombre="Coosalud")
    db.add(a)
    db.flush()
    assert a.activo is True


def test_tratamientos_n_a_m_sin_duplicados(db, seed):
    at = db.query(Atencion).first()
    t = db.execute(text("INSERT INTO tratamiento (nombre) VALUES ('Operatoria') RETURNING id_tratamiento")).scalar_one()
    db.execute(text("INSERT INTO atencion_x_tratamiento VALUES (:a, :t)"), {"a": at.id_atencion, "t": t})
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO atencion_x_tratamiento VALUES (:a, :t)"), {"a": at.id_atencion, "t": t})


def test_cola_de_revision_conserva_la_fila_original(db):
    imp = db.execute(
        text(
            "INSERT INTO importacion (tipo, nombre_archivo, total_registros) "
            "VALUES ('atenciones', 'atenciones_septiembre.xlsx', 120) RETURNING id_importacion"
        )
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO importacion_fila (id_importacion, numero_fila, motivo, datos) "
            "VALUES (:i, 7, 'diagnóstico sin coincidencia', CAST(:d AS jsonb))"
        ),
        {"i": imp, "d": '{"DOCUMENTO DE IDENTIDAD": "123", "DIAGNÓSTICO BUCAL 1": "caries??"}'},
    )
    fila = db.execute(text("SELECT estado, datos->>'DIAGNÓSTICO BUCAL 1' FROM importacion_fila")).one()
    assert tuple(fila) == ("revision", "caries??")


def test_checks_de_importacion(db):
    for sql in (
        "INSERT INTO importacion (tipo, nombre_archivo) VALUES ('otro', 'x')",
        "INSERT INTO importacion (tipo, nombre_archivo, estado) VALUES ('cie10', 'x', 'raro')",
    ):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(sql))
