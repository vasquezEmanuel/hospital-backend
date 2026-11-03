"""Pruebas de auditoría y control de acceso por rol (Sprint 4: regla 6 y roles vía proveedor de identidad)."""

from datetime import datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.middleware.auditoria import get_auditor
from app.models import Profesional
from app.repositories.imagen_repo import COLOMBIA
from app.routers import auditoria, enfermedades, expediente, imagenes, pacientes
from app.services import auditoria_service
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
NUEVO = {"tipo_documento": "CC", "documento_identidad": "52880143", "nombre": "Ana Martínez"}


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a
    return a


@pytest.fixture
def con_roles(db):
    """Fábrica de clientes con los roles que traería el token del proveedor de identidad."""
    app.dependency_overrides[get_db] = lambda: db

    def crear(*roles, sub="auth|otro"):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            sub=sub, email=f"{sub}@hospital.test", roles=frozenset(roles)
        )
        return TestClient(app)

    yield crear
    app.dependency_overrides.clear()


def _eventos(db):
    return db.execute(
        text(
            "SELECT accion, entidad_afectada, id_paciente, auth_sub, ip_origen, detalle, id_profesional "
            "FROM auditoria ORDER BY id_evento"
        )
    ).all()


def test_cada_ruta_de_datos_de_pacientes_declara_el_auditor():
    # Se recorren los routers (interfaz pública de FastAPI), no app.routes, cuya forma interna cambia entre versiones.
    # Un router nuevo que toque datos de pacientes debe agregarse aquí: por eso la lista es explícita.
    routers = (pacientes.router, expediente.router, imagenes.router, enfermedades.router, auditoria.router)
    rutas = [r for router in routers for r in router.routes if isinstance(r, APIRoute)]
    assert len(rutas) == 11  # si se agrega una ruta, esta prueba obliga a decidir cómo se audita
    sin_auditor = [
        f"{sorted(r.methods)} {r.path}"
        for r in rutas
        if not any(d.call is get_auditor for d in r.dependant.dependencies)
    ]
    assert sin_auditor == []


def test_consultas_y_cambios_de_pacientes_quedan_registrados_sin_datos_clinicos(client, seed, db):
    maria = seed["maria"].id_paciente
    client.get("/api/v1/pacientes", params={"q": "maria", "sexo": "F"})
    client.get(f"/api/v1/pacientes/{maria}")
    client.get(f"/api/v1/pacientes/{maria}/expediente")
    client.patch(f"/api/v1/pacientes/{maria}", json={"telefono": "3001234567"})
    assert client.post("/api/v1/pacientes", json=NUEVO).status_code == 201

    eventos = _eventos(db)
    assert [(e.accion, e.id_paciente) for e in eventos] == [
        ("consultar_pacientes", None),
        ("consultar_paciente", maria),
        ("consultar_expediente", maria),
        ("editar_paciente", maria),
        ("crear_paciente", None),
    ]
    assert {e.auth_sub for e in eventos} == {"auth|test"} and {e.entidad_afectada for e in eventos} == {"paciente"}
    assert eventos[0].detalle == {"filtros": ["q", "sexo"]} and eventos[3].detalle == {"campos": ["telefono"]}
    assert eventos[0].ip_origen == "testclient"
    volcado = str([e.detalle for e in eventos]).lower()
    assert "maria" not in volcado and "3001234567" not in volcado  # nombres de filtros y campos, nunca sus valores


def test_imagenes_subir_listar_ver_e_inactivar_quedan_registrados(client, seed, db, almacen):
    maria = seed["maria"].id_paciente
    creada = client.post(
        "/api/v1/imagenes", data={"id_paciente": str(maria)}, files={"archivo": ("a.jpg", JPEG, "image/jpeg")}
    ).json()
    client.get("/api/v1/imagenes", params={"id_paciente": maria, "q": "x"})
    client.get(f"/api/v1/imagenes/{creada['id_imagen']}")
    client.delete(f"/api/v1/imagenes/{creada['id_imagen']}")
    eventos = _eventos(db)
    # el paciente de una imagen se deduce de la propia imagen
    assert [(e.accion, e.id_paciente) for e in eventos] == [
        ("subir_imagen", maria),
        ("consultar_imagenes", maria),
        ("consultar_imagen", maria),
        ("inactivar_imagen", maria),
    ]
    assert eventos[2].detalle == {"id_imagen": creada["id_imagen"]}
    assert eventos[1].detalle == {"filtros": ["id_paciente", "q"]}


def test_el_usuario_se_enlaza_con_su_fila_de_profesional_si_existe(client, seed, db):
    client.get(f"/api/v1/pacientes/{seed['maria'].id_paciente}")
    profesional = Profesional(nombre="Dra. Laura Castaño", identificacion="1", correo="l@h.test", auth_id="auth|test")
    db.add(profesional)
    db.flush()
    client.get(f"/api/v1/pacientes/{seed['maria'].id_paciente}")
    sin_fila, con_fila = _eventos(db)
    assert sin_fila.id_profesional is None and sin_fila.auth_sub == "auth|test"  # nunca queda sin saber quién fue
    assert con_fila.id_profesional == profesional.id_profesional


def test_si_la_auditoria_falla_no_se_entregan_ni_se_cambian_datos(client, seed, db, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("la auditoría no responde")

    monkeypatch.setattr(auditoria_service, "registrar", falla)
    with pytest.raises(RuntimeError):
        client.get(f"/api/v1/pacientes/{seed['maria'].id_paciente}")
    with pytest.raises(RuntimeError):
        client.post("/api/v1/pacientes", json=NUEVO)
    assert db.execute(text("SELECT count(*) FROM paciente WHERE documento_identidad = '52880143'")).scalar_one() == 0


def test_la_auditoria_es_inmutable_y_siempre_dice_quien_actuo(client, seed, db):
    client.get(f"/api/v1/pacientes/{seed['maria'].id_paciente}")
    for sql in ("UPDATE auditoria SET accion = 'x'", "DELETE FROM auditoria", "TRUNCATE auditoria"):
        with pytest.raises(DBAPIError, match="inmutable"), db.begin_nested():
            db.execute(text(sql))
    with pytest.raises(IntegrityError), db.begin_nested():  # ni profesional ni usuario del IdP: no se acepta
        db.execute(text("INSERT INTO auditoria (accion) VALUES ('anonimo')"))
    assert len(_eventos(db)) == 1


def test_sin_el_rol_clinico_no_hay_acceso_y_no_se_registra_nada(con_roles, seed, db):
    visitante = con_roles("paciente")
    assert visitante.get("/api/v1/pacientes").status_code == 403
    assert visitante.get("/api/v1/enfermedades/K021/pacientes").status_code == 403
    assert visitante.get("/api/v1/auditoria").status_code == 403
    assert _eventos(db) == []


def test_la_auditoria_solo_la_ve_el_administrador(con_roles, anon_client):
    assert anon_client.get("/api/v1/auditoria").status_code == 401
    assert con_roles("odontologo").get("/api/v1/auditoria").status_code == 403
    assert con_roles("administrador", sub="auth|admin").get("/api/v1/auditoria").status_code == 200


def test_consultar_la_auditoria_filtra_pagina_y_tambien_queda_registrada(con_roles, seed, db):
    maria, carlos = seed["maria"].id_paciente, seed["carlos"].id_paciente
    db.add(Profesional(nombre="Dra. Laura Castaño", identificacion="1", correo="l@h.test", auth_id="auth|dra"))
    db.flush()
    dra = con_roles("odontologo", sub="auth|dra")
    dra.get(f"/api/v1/pacientes/{maria}")
    dra.get(f"/api/v1/pacientes/{carlos}")
    dra.get(f"/api/v1/pacientes/{maria}/expediente")

    admin = con_roles("administrador", sub="auth|admin")
    todo = admin.get("/api/v1/auditoria").json()
    assert todo["total"] == 4  # las 3 consultas de la doctora y esta misma consulta de auditoría
    assert todo["items"][0]["accion"] == "consultar_auditoria"  # lo más reciente primero
    assert admin.get("/api/v1/auditoria", params={"id_paciente": maria}).json()["total"] == 2
    assert admin.get("/api/v1/auditoria", params={"accion": "consultar_expediente"}).json()["total"] == 1
    por_usuario = admin.get("/api/v1/auditoria", params={"auth_sub": "auth|dra"}).json()
    assert por_usuario["total"] == 3 and {i["profesional_nombre"] for i in por_usuario["items"]} == {
        "Dra. Laura Castaño"
    }
    hoy = datetime.now(COLOMBIA).date()
    assert admin.get("/api/v1/auditoria", params={"fecha_desde": hoy.isoformat()}).json()["total"] >= 3
    assert (
        admin.get("/api/v1/auditoria", params={"fecha_hasta": (hoy - timedelta(days=2)).isoformat()}).json()["total"]
        == 0
    )
    pagina = admin.get("/api/v1/auditoria", params={"page_size": 2, "page": 2}).json()
    assert len(pagina["items"]) == 2 and pagina["total"] >= 7
    propios = [e for e in _eventos(db) if e.accion == "consultar_auditoria"]
    assert propios[0].detalle == {"filtros": []} and propios[1].detalle == {"filtros": ["id_paciente"]}
