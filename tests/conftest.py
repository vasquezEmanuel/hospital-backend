"""Fixtures: Postgres real (nunca SQLite: el esquema usa triggers y tipos propios de PostgreSQL).

La base de pruebas se construye con `alembic upgrade head`, así cada corrida prueba también las migraciones.
Cada test corre dentro de una transacción que se revierte al terminar.
"""

import os
from datetime import date

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hospital_test")
os.environ["DATABASE_URL"] = TEST_URL  # antes de importar la app

from app.core.config import get_settings  # noqa: E402
from app.core.security import CurrentUser, get_current_user  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Aseguradora, Atencion, Cie10, Paciente  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(get_settings().sqlalchemy_url)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    conn.close()


def _user(roles):
    return CurrentUser(sub="auth|test", email="t@hospital.test", roles=frozenset(roles))


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _user(["odontologo"])
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(db):
    """Sin override de autenticación: prueba el comportamiento real de seguridad."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seed(db):
    sura = Aseguradora(nombre="SURA")
    maria = Paciente(
        tipo_documento="CC",
        documento_identidad="1025847210",
        nombre="María Rodríguez",
        sexo="F",
        fecha_nacimiento=date(1984, 3, 1),
        ciudad="Bogotá D.C.",
    )
    carlos = Paciente(tipo_documento="CC", documento_identidad="79421880", nombre="Carlos Gómez", sexo="M")
    db.add_all(
        [
            sura,
            maria,
            carlos,
            Cie10(
                cod_4="K021",
                cod_3="K02",
                descripcion_3="Caries dental",
                descripcion_4="Caries de la dentina",
                es_odontologico=True,
            ),
            Cie10(
                cod_4="C187",
                cod_3="C18",
                descripcion_3="Tumor maligno del colon",
                descripcion_4="Tumor maligno del colon sigmoide",
                es_odontologico=False,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            Atencion(
                id_paciente=maria.id_paciente, fecha_atencion=date(2026, 8, 18), id_aseguradora=sura.id_aseguradora
            ),
            Atencion(
                id_paciente=maria.id_paciente, fecha_atencion=date(2026, 9, 12), id_aseguradora=sura.id_aseguradora
            ),
        ]
    )
    db.flush()
    return {"maria": maria, "carlos": carlos}
