"""Sprint 7: atenciones (alta, lista, detalle) y catálogos aseguradora / tratamiento / profesional."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.security import CurrentUser, get_current_user
from app.main import app
from app.models import Aseguradora, Cie10, Profesional, Tratamiento
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento

A = "/api/v1/atenciones"


@pytest.fixture(autouse=True)
def _almacen(tmp_path):
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")


@pytest.fixture
def cat(db, seed):
    trat = [Tratamiento(nombre="Operatoria"), Tratamiento(nombre="RX"), Tratamiento(nombre="Inactivo", activo=False)]
    prof = Profesional(nombre="Dra. Gloria Alvarez", identificacion="555", correo="g@h.co", auth_id="auth|test")
    db.add_all(trat + [prof, Aseguradora(nombre="Inactiva", activo=False)])
    db.flush()
    sura = db.query(Aseguradora).filter_by(nombre="SURA").one()
    inactiva = db.query(Aseguradora).filter_by(nombre="Inactiva").one()
    return {"trat": trat, "prof": prof, "sura": sura, "inactiva": inactiva, **seed}


def _cuerpo(cat, **extra):
    base = {
        "id_paciente": str(cat["maria"].public_id),
        "fecha_atencion": "2026-10-01",
        "id_aseguradora": cat["sura"].id_aseguradora,
        "ubicacion": "Piso 3",
        "ids_tratamientos": [cat["trat"][0].id_tratamiento, cat["trat"][1].id_tratamiento],
        "diagnostico_hospitalario": {"descripcion_original": "Tumor de colon", "cod_4": "C18.7"},
        "diagnosticos_bucales": [{"descripcion": "Caries", "codigos": ["k02.1", "K021"]}],
        "plan_tratamiento": "Operatoria",
    }
    base.update(extra)
    return base


def test_crear_atencion_completa_y_ver_detalle(client, cat, db):
    r = client.post(A, json=_cuerpo(cat))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["diagnostico_hospitalario"]["codigo"]["cod_4"] == "C187"
    assert [c["cod_4"] for c in d["diagnosticos_bucales"][0]["codigos"]] == ["K021"]  # sin duplicados
    assert [t["nombre"] for t in d["tratamientos"]] == ["Operatoria", "RX"]
    assert d["profesional"] == "Dra. Gloria Alvarez"  # enlazado por el sub del usuario (auth_id)
    assert d["paciente"]["nombre"] == "María Rodríguez"
    assert d["codigo_atencion"].startswith("A")
    again = client.get(f"{A}/{d['id_atencion']}")
    assert again.status_code == 200 and again.json()["id_atencion"] == d["id_atencion"]


def test_la_atencion_aparece_en_lista_expediente_y_busqueda_por_enfermedad(client, cat):
    client.post(A, json=_cuerpo(cat))
    lista = client.get(A, params={"cod_4": "K02.1"}).json()
    assert lista["total"] == 1 and lista["items"][0]["diagnosticos_bucales"] == ["Caries"]
    exp = client.get(f"/api/v1/pacientes/{cat['maria'].public_id}/expediente").json()
    assert len(exp["atenciones"]) == 3
    assert any(t["nombre"] == "RX" for a in exp["atenciones"] for t in a["tratamientos"])
    enf = client.get("/api/v1/enfermedades/K021/pacientes").json()
    assert enf["total"] == 1


def test_lista_filtros(client, cat):
    todas = client.get(A).json()
    assert todas["total"] == 2  # las 2 del seed
    assert client.get(A, params={"q": "maria"}).json()["total"] == 2
    assert client.get(A, params={"q": "carlos"}).json()["total"] == 0
    assert client.get(A, params={"fecha_desde": "2026-09-01"}).json()["total"] == 1
    assert client.get(A, params={"id_aseguradora": cat["sura"].id_aseguradora}).json()["total"] == 2
    assert client.get(A, params={"id_paciente": str(cat["maria"].public_id)}).json()["total"] == 2
    assert client.get(A, params={"id_paciente": "00000000-0000-0000-0000-000000000000"}).json()["total"] == 0
    assert client.get(A, params={"id_paciente": "1"}).status_code == 422


@pytest.mark.parametrize(
    ("cambio", "codigo"),
    [
        ({"id_paciente": "00000000-0000-0000-0000-000000000000"}, 404),
        ({"fecha_atencion": str(date.today() + timedelta(days=2))}, 422),
        ({"diagnosticos_bucales": [{"descripcion": "x", "codigos": []}]}, 422),
        ({"diagnosticos_bucales": [{"descripcion": "Caries", "codigos": ["C187"]}]}, 422),  # no odontológico
        ({"diagnosticos_bucales": [{"descripcion": "Caries", "codigos": ["Z000"]}]}, 422),  # no existe
        ({"diagnostico_hospitalario": {"descripcion_original": "x", "cod_4": "Z000"}}, 422),
        ({"ids_tratamientos": [999999]}, 422),
        ({"id_aseguradora": 999999}, 422),
        ({"id_profesional": 999999}, 422),
    ],
)
def test_validaciones(client, cat, cambio, codigo):
    r = client.post(A, json=_cuerpo(cat, **cambio))
    assert r.status_code == codigo, r.text


def test_inactivos_se_rechazan_y_no_queda_nada_guardado(client, cat, db):
    antes = db.execute(text("SELECT count(*) FROM atencion")).scalar_one()
    assert client.post(A, json=_cuerpo(cat, id_aseguradora=cat["inactiva"].id_aseguradora)).status_code == 422
    assert client.post(A, json=_cuerpo(cat, ids_tratamientos=[cat["trat"][2].id_tratamiento])).status_code == 422
    assert db.execute(text("SELECT count(*) FROM atencion")).scalar_one() == antes


def test_hospitalario_es_opcional_y_se_acepta_solo_texto(client, cat):
    r = client.post(
        A,
        json=_cuerpo(
            cat,
            diagnostico_hospitalario={"descripcion_original": "Pendiente de codificar"},
            diagnosticos_bucales=[],
            ids_tratamientos=[],
        ),
    )
    assert r.status_code == 201
    assert r.json()["diagnostico_hospitalario"]["codigo"] is None and r.json()["diagnosticos_bucales"] == []


def test_profesional_texto_tiene_prioridad_sobre_el_enlazado(client, cat):
    r = client.post(A, json=_cuerpo(cat, profesional_texto="Dr. Externo"))
    assert r.json()["profesional"] == "Dr. Externo"


def test_detalle_inexistente_404_y_uuid_numerico_422(client, cat):
    assert client.get(f"{A}/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{A}/5").status_code == 422


def test_imagen_se_asocia_a_la_atencion_creada(client, cat):
    d = client.post(A, json=_cuerpo(cat)).json()
    r = client.post(
        "/api/v1/imagenes",
        data={"id_paciente": d["paciente"]["id_paciente"], "id_atencion": d["id_atencion"]},
        files={"archivo": ("f.jpg", b"\xff\xd8\xff\xe0" + b"0" * 64, "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    assert len(client.get(f"{A}/{d['id_atencion']}").json()["imagenes"]) == 1


def test_auditoria_de_atenciones(client, cat, db):
    d = client.post(A, json=_cuerpo(cat)).json()
    client.get(A)
    client.get(f"{A}/{d['id_atencion']}")
    acciones = [a for (a,) in db.execute(text("SELECT accion FROM auditoria ORDER BY id_evento"))]
    assert acciones[0] == "crear_atencion"
    assert "consultar_atenciones" in acciones and "consultar_atencion" in acciones


def test_solo_personal_clinico_accede(db, cat):
    from app.db.session import get_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="x", email=None, roles=frozenset({"otro"}))
    from fastapi.testclient import TestClient

    c = TestClient(app)
    assert c.get(A).status_code == 403
    assert c.post(A, json=_cuerpo(cat)).status_code == 403
    app.dependency_overrides.clear()


# --- catálogos ------------------------------------------------------------------------------------------------


@pytest.fixture
def admin(db):
    from fastapi.testclient import TestClient

    from app.db.session import get_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="auth|admin", email="a@h.co", roles=frozenset({"administrador"})
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("ruta", ["aseguradoras", "tratamientos"])
def test_catalogo_crud_y_unicidad(admin, ruta):
    base = f"/api/v1/{ruta}"
    r = admin.post(base, json={"nombre": "  Nueva   Entrada "})
    assert r.status_code == 201 and r.json()["nombre"] == "Nueva Entrada"
    id_ = r.json()["id"]
    assert admin.post(base, json={"nombre": "nueva entrada"}).status_code == 409
    assert admin.patch(f"{base}/{id_}", json={"nombre": "Otra"}).json()["nombre"] == "Otra"
    assert admin.patch(f"{base}/{id_}", json={"activo": False}).json()["activo"] is False
    assert id_ not in [x["id"] for x in admin.get(base).json()]
    assert id_ in [x["id"] for x in admin.get(base, params={"incluir_inactivas": True}).json()]
    assert admin.patch(f"{base}/999999", json={"nombre": "Zz"}).status_code == 404
    otro = admin.post(base, json={"nombre": "Segunda"}).json()["id"]
    assert admin.patch(f"{base}/{otro}", json={"nombre": "OTRA"}).status_code == 409


def test_catalogo_escritura_solo_administrador(client):
    assert client.get("/api/v1/aseguradoras").status_code == 200
    assert client.post("/api/v1/aseguradoras", json={"nombre": "Zeta"}).status_code == 403
    assert client.post("/api/v1/tratamientos", json={"nombre": "Zeta"}).status_code == 403
    assert client.patch("/api/v1/profesionales/1", json={"activo": False}).status_code == 403


def test_profesionales_crud_enlace_y_yo(admin, db):
    datos = {"nombre": "Dr. Nuevo Prueba", "identificacion": "1234", "correo": "n@h.co", "auth_id": "auth|admin"}
    r = admin.post("/api/v1/profesionales", json=datos)
    assert r.status_code == 201 and r.json()["auth_id"] == "auth|admin"
    id_ = r.json()["id_profesional"]
    assert admin.post("/api/v1/profesionales", json={**datos, "identificacion": "9999"}).status_code == 409
    assert admin.get("/api/v1/profesionales/yo").json()["nombre"] == "Dr. Nuevo Prueba"
    assert "correo" not in admin.get("/api/v1/profesionales").json()[0]  # la lista no expone datos personales
    assert (
        admin.patch(f"/api/v1/profesionales/{id_}", json={"especializacion": "Cirugía"}).json()["especializacion"]
        == "Cirugía"
    )
    assert admin.patch(f"/api/v1/profesionales/{id_}", json={"activo": False}).json()["activo"] is False
    assert admin.patch("/api/v1/profesionales/999999", json={"activo": False}).status_code == 404
    otro = admin.post(
        "/api/v1/profesionales", json={"nombre": "Otro Dr", "identificacion": "4321", "correo": "o@h.co"}
    ).json()["id_profesional"]
    assert admin.patch(f"/api/v1/profesionales/{otro}", json={"correo": "n@h.co"}).status_code == 409


def test_yo_sin_enlace_404(client):
    assert client.get("/api/v1/profesionales/yo").status_code == 404


def test_cie10_no_odontologico_no_se_cuela_por_trigger(db, cat):
    """Red de seguridad: aunque se salte el servicio, la base rechaza un código no odontológico (regla 2)."""
    from sqlalchemy.exc import DBAPIError

    db.execute(
        text("INSERT INTO diagnostico_bucal (id_atencion, descripcion) SELECT id_atencion, 'x' FROM atencion LIMIT 1")
    )
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO cie10_x_diagnostico_bucal (cod_4, id_diagnostico_bucal) "
                "SELECT 'C187', max(id_diagnostico_bucal) FROM diagnostico_bucal"
            )
        )
    assert Cie10  # importado para dejar claro de qué entidad se trata
