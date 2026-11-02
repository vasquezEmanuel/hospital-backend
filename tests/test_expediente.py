"""Pruebas del expediente del paciente (Sprint 3: búsqueda por paciente -> enfermedades e imágenes)."""

from datetime import date

import pytest

from app.main import app
from app.models import Atencion, Cie10, DiagnosticoBucal, DiagnosticoHospitalario
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 64


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a
    return a


def _subir(client, id_paciente, contenido, **extra):
    return client.post(
        "/api/v1/imagenes",
        data={"id_paciente": str(id_paciente), **{k: str(v) for k, v in extra.items()}},
        files={"archivo": ("f.jpg", contenido, "image/jpeg")},
    )


def test_expediente_reune_atenciones_diagnosticos_e_imagenes(client, seed, db, almacen):
    maria = seed["maria"]
    reciente, antigua = (
        db.query(Atencion).filter_by(id_paciente=maria.id_paciente).order_by(Atencion.fecha_atencion.desc()).all()
    )
    reciente.ubicacion, reciente.profesional_texto = "Consulta externa 3", "Dra. Laura Castaño"
    db.add(DiagnosticoHospitalario(id_atencion=reciente.id_atencion, descripcion_original="C187-COLON", cod_4="C187"))
    con_codigo = DiagnosticoBucal(id_atencion=reciente.id_atencion, descripcion="Caries")
    con_codigo.codigos = [db.get(Cie10, "K021")]
    sin_codigo = DiagnosticoBucal(id_atencion=reciente.id_atencion, descripcion="Mucositis por quimioterapia")
    db.add_all([con_codigo, sin_codigo])
    db.flush()
    _subir(client, maria.id_paciente, JPEG, id_diagnostico_bucal=con_codigo.id_diagnostico_bucal)
    _subir(client, maria.id_paciente, PNG)  # solo del paciente, sin atención

    r = client.get(f"/api/v1/pacientes/{maria.id_paciente}/expediente")
    assert r.status_code == 200
    body = r.json()
    assert body["paciente"]["nombre"] == "María Rodríguez" and body["total_imagenes"] == 2
    assert [a["fecha_atencion"] for a in body["atenciones"]] == ["2026-09-12", "2026-08-18"]  # reciente primero
    a1, a2 = body["atenciones"]
    assert a1["aseguradora"] == "SURA" and a1["profesional"] == "Dra. Laura Castaño"
    assert a1["diagnostico_hospitalario"]["codigo"] == {
        "cod_4": "C187",
        "descripcion": "Tumor maligno del colon sigmoide",
        "es_odontologico": False,
    }
    bucales = {d["descripcion"]: d for d in a1["diagnosticos_bucales"]}
    assert bucales["Caries"]["codificado"] is True and bucales["Caries"]["codigos"][0]["cod_4"] == "K021"
    assert bucales["Mucositis por quimioterapia"]["codificado"] is False  # solo texto: pendiente de codificar
    assert len(a1["imagenes"]) == 1 and a1["imagenes"][0]["url"].startswith("http://testserver/api/v1/archivos/")
    assert a2["diagnostico_hospitalario"] is None and a2["diagnosticos_bucales"] == [] and a2["imagenes"] == []
    assert len(body["imagenes_sin_atencion"]) == 1


def test_expediente_no_incluye_imagenes_inactivas(client, seed, almacen):
    pid = seed["maria"].id_paciente
    id_imagen = _subir(client, pid, JPEG).json()["id_imagen"]
    client.delete(f"/api/v1/imagenes/{id_imagen}")
    body = client.get(f"/api/v1/pacientes/{pid}/expediente").json()
    assert body["total_imagenes"] == 0 and body["imagenes_sin_atencion"] == []


def test_expediente_de_un_paciente_sin_atenciones(client, seed, almacen):
    body = client.get(f"/api/v1/pacientes/{seed['carlos'].id_paciente}/expediente").json()
    assert body["atenciones"] == [] and body["total_imagenes"] == 0


def test_expediente_inexistente_es_404(client, almacen):
    assert client.get("/api/v1/pacientes/999999/expediente").status_code == 404


def test_expediente_exige_sesion(anon_client, almacen):
    assert anon_client.get("/api/v1/pacientes/1/expediente").status_code == 401


def test_atencion_sin_diagnosticos_ni_imagenes_sale_vacia_pero_presente(client, seed, db, almacen):
    db.add(Atencion(id_paciente=seed["carlos"].id_paciente, fecha_atencion=date(2026, 1, 5)))
    db.flush()
    body = client.get(f"/api/v1/pacientes/{seed['carlos'].id_paciente}/expediente").json()
    (atencion,) = body["atenciones"]
    assert atencion["fecha_atencion"] == "2026-01-05" and atencion["diagnosticos_bucales"] == []
    assert atencion["diagnostico_hospitalario"] is None and atencion["imagenes"] == []
