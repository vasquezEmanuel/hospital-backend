"""Reglas que viven en la BD (schema.sql): el trigger de CIE-10 odontológico y la unicidad del documento."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Atencion


def test_trigger_rechaza_codigo_no_odontologico_en_diagnostico_bucal(db, seed):
    maria = seed["maria"]
    at = db.query(Atencion).filter_by(id_paciente=maria.id_paciente).first()
    dx = db.execute(
        text(
            "INSERT INTO diagnostico_bucal (id_atencion, descripcion) VALUES (:a, 'x') RETURNING id_diagnostico_bucal"
        ),
        {"a": at.id_atencion},
    ).scalar_one()
    db.execute(text("INSERT INTO cie10_x_diagnostico_bucal VALUES ('K021', :d)"), {"d": dx})  # odontológico: ok
    with pytest.raises(DBAPIError, match="no está marcado como odontológico"):
        with db.begin_nested():
            db.execute(text("INSERT INTO cie10_x_diagnostico_bucal VALUES ('C187', :d)"), {"d": dx})


def test_documento_unico_a_nivel_de_bd(db, seed):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO paciente (documento_identidad, nombre) VALUES ('79421880', 'Dup')"))


def test_check_tipo_documento_y_sexo(db):
    consultas = (
        "INSERT INTO paciente (documento_identidad, nombre, tipo_documento) VALUES ('555555', 'N', 'XX')",
        "INSERT INTO paciente (documento_identidad, nombre, sexo) VALUES ('555555', 'N', 'Z')",
    )
    for sql in consultas:
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(sql))
