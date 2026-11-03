"""Pruebas de la búsqueda por enfermedad -> pacientes (Sprint 4: búsqueda integrada, reglas 5, 6 y 7)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Atencion, Cie10, DiagnosticoBucal, DiagnosticoHospitalario
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a
    return a


@pytest.fixture
def datos(db, seed):
    """María: atención reciente con C187, Caries (K021) y Mucositis (solo texto). Carlos: C187 y K021."""
    maria, carlos = seed["maria"], seed["carlos"]
    reciente = (
        db.query(Atencion).filter_by(id_paciente=maria.id_paciente).order_by(Atencion.fecha_atencion.desc()).first()
    )
    hosp_maria = DiagnosticoHospitalario(
        id_atencion=reciente.id_atencion, descripcion_original="C187-TUMOR MALIGNO DEL COLON", cod_4="C187"
    )
    caries = DiagnosticoBucal(id_atencion=reciente.id_atencion, descripcion="Caries")
    caries.codigos = [db.get(Cie10, "K021")]
    mucositis = DiagnosticoBucal(id_atencion=reciente.id_atencion, descripcion="Mucositis por quimioterapia")
    atencion_carlos = Atencion(id_paciente=carlos.id_paciente, fecha_atencion=date(2026, 7, 7))
    db.add_all([hosp_maria, caries, mucositis, atencion_carlos])
    db.flush()
    hosp_carlos = DiagnosticoHospitalario(
        id_atencion=atencion_carlos.id_atencion, descripcion_original="C187", cod_4="C187"
    )
    resto = DiagnosticoBucal(id_atencion=atencion_carlos.id_atencion, descripcion="Resto radicular")
    resto.codigos = [db.get(Cie10, "K021")]
    db.add_all([hosp_carlos, resto])
    db.flush()
    return {"maria": maria, "carlos": carlos, "caries": caries, "hosp_carlos": hosp_carlos, "reciente": reciente}


def _buscar(client, cod, **params):
    return client.get(f"/api/v1/enfermedades/{cod}/pacientes", params=params)


def test_busqueda_por_diagnostico_de_hospitalizacion_como_en_la_pantalla_de_diagnosticos(client, datos, almacen):
    r = _buscar(client, "C187")
    assert r.status_code == 200
    body = r.json()
    assert body["codigo"] == {
        "cod_4": "C187",
        "descripcion": "Tumor maligno del colon sigmoide",
        "es_odontologico": False,
    }
    assert body["total"] == 2 and [i["fecha_atencion"] for i in body["items"]] == ["2026-09-12", "2026-07-07"]
    maria, carlos = body["items"]
    assert maria["documento_identidad"] == "1025847210" and maria["nombre"] == "María Rodríguez"
    assert maria["codigo_paciente"] == f"P-{datos['maria'].id_paciente:03d}"
    assert maria["coincide_en"] == ["hospitalizacion"]
    assert maria["diagnostico_hospitalario"] == "C187-TUMOR MALIGNO DEL COLON"
    assert maria["diagnosticos_bucales"] == ["Caries", "Mucositis por quimioterapia"]  # todos los de la atención
    assert carlos["nombre"] == "Carlos Gómez" and carlos["diagnosticos_bucales"] == ["Resto radicular"]


def test_busqueda_por_diagnostico_bucal_y_el_ambito_filtra(client, datos, almacen):
    bucal = _buscar(client, "K021", en="bucal").json()
    assert bucal["total"] == 2 and all(i["coincide_en"] == ["bucal"] for i in bucal["items"])
    assert bucal["codigo"]["es_odontologico"] is True
    assert _buscar(client, "K021", en="hospitalizacion").json() == {
        "codigo": bucal["codigo"],
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    assert (
        _buscar(client, "C187", en="bucal").json()["total"] == 0
    )  # un código no odontológico no está en diagnósticos bucales


def test_si_el_codigo_esta_en_hospitalizacion_y_en_bucal_la_atencion_sale_una_sola_vez(client, datos, almacen):
    datos["hosp_carlos"].cod_4 = "K021"  # el diagnóstico de hospitalización puede ser cualquier código CIE-10
    body = _buscar(client, "K021").json()
    assert body["total"] == 2
    por_nombre = {i["nombre"]: i["coincide_en"] for i in body["items"]}
    assert por_nombre == {"María Rodríguez": ["bucal"], "Carlos Gómez": ["hospitalizacion", "bucal"]}


def test_el_codigo_se_normaliza_y_uno_inexistente_es_404(client, datos, almacen):
    assert _buscar(client, "c18.7").json()["total"] == 2
    assert _buscar(client, "k02.1", en="bucal").json()["total"] == 2
    assert _buscar(client, "ZZZZ").status_code == 404
    assert _buscar(client, "A000").json() == {"detail": "Código CIE-10 no encontrado"}


def test_regla_5_solo_cuentan_los_diagnosticos_activos(client, datos, almacen):
    datos["caries"].activo = False
    assert _buscar(client, "K021", en="bucal").json()["total"] == 1
    datos["hosp_carlos"].activo = False
    assert _buscar(client, "C187").json()["total"] == 1


def test_imagenes_recientes_con_enlace_firmado_y_total(client, datos, almacen):
    maria = datos["maria"].id_paciente
    ids = []
    for i in range(4):
        r = client.post(
            "/api/v1/imagenes",
            data={"id_paciente": str(maria)},
            files={"archivo": (f"{i}.jpg", JPEG + bytes([i]), "image/jpeg")},
        )
        ids.append(r.json()["id_imagen"])
    fila = _buscar(client, "C187").json()["items"][0]
    assert fila["total_imagenes"] == 4 and len(fila["imagenes"]) == 3  # por defecto, las 3 más recientes
    assert [i["id_imagen"] for i in fila["imagenes"]] == ids[::-1][:3]
    assert all(i["url"].startswith("http://testserver/api/v1/archivos/") for i in fila["imagenes"])
    assert _buscar(client, "C187", max_imagenes=0).json()["items"][0]["imagenes"] == []
    assert len(_buscar(client, "C187", max_imagenes=10).json()["items"][0]["imagenes"]) == 4
    client.delete(f"/api/v1/imagenes/{ids[0]}")  # regla 5: una imagen inactiva no cuenta
    assert _buscar(client, "C187").json()["items"][0]["total_imagenes"] == 3
    assert _buscar(client, "C187").json()["items"][1]["total_imagenes"] == 0  # Carlos no tiene imágenes


def test_paginacion(client, datos, almacen):
    pagina_2 = _buscar(client, "C187", page_size=1, page=2).json()
    assert pagina_2["total"] == 2 and [i["nombre"] for i in pagina_2["items"]] == ["Carlos Gómez"]


def test_regla_6_cada_paciente_expuesto_queda_en_auditoria_una_sola_vez(client, datos, db, almacen):
    antigua = (
        db.query(Atencion).filter_by(id_paciente=datos["maria"].id_paciente).order_by(Atencion.fecha_atencion).first()
    )
    db.add(DiagnosticoHospitalario(id_atencion=antigua.id_atencion, descripcion_original="C187", cod_4="C187"))
    db.flush()
    assert _buscar(client, "C187").json()["total"] == 3  # tres atenciones, dos pacientes
    _buscar(client, "K021", en="hospitalizacion")  # sin resultados: queda un solo evento, sin paciente
    eventos = db.execute(text("SELECT id_paciente, detalle FROM auditoria ORDER BY id_evento")).all()
    assert [e.id_paciente for e in eventos] == [datos["maria"].id_paciente, datos["carlos"].id_paciente, None]
    assert eventos[0].detalle == {"cod_4": "C187", "en": "cualquiera"}
    assert eventos[2].detalle == {"cod_4": "K021", "en": "hospitalizacion"}


def test_validaciones_de_entrada(client, datos, almacen):
    assert _buscar(client, "C187", en="otro").status_code == 422
    assert _buscar(client, "C187", max_imagenes=11).status_code == 422
    assert _buscar(client, "C187", page=0).status_code == 422


def test_sin_sesion_no_hay_acceso(anon_client, datos, almacen):
    assert _buscar(anon_client, "C187").status_code == 401


def test_un_rol_ajeno_a_la_clinica_recibe_403(db, datos, almacen):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="x", roles=frozenset({"paciente"}))
    try:
        assert _buscar(TestClient(app), "C187").status_code == 403
    finally:
        app.dependency_overrides.clear()
