"""Sprint 8: importación por API (catálogo CIE-10 una sola vez, atenciones, cola de revisión) e imágenes en lote."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento
from scripts.generar_datos_demo import crear_atenciones_demo, crear_catalogo_demo

RUTA = "/api/v1/importaciones"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def admin(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="auth|admin", email="a@h.co", roles=frozenset({"administrador"})
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def archivos(tmp_path):
    return crear_catalogo_demo(tmp_path / "c.xlsx"), crear_atenciones_demo(tmp_path / "a.xlsx")


def _subir(c, ruta, destino, nombre=None, tipo=XLSX, **data):
    with open(ruta, "rb") as f:
        return c.post(f"{RUTA}/{destino}", files={"archivo": (nombre or ruta.name, f.read(), tipo)}, data=data)


def test_catalogo_se_carga_una_sola_vez(admin, archivos, db):
    r = _subir(admin, archivos[0], "catalogo-cie10")
    assert r.status_code == 201, r.text
    assert (r.json()["insertados"], r.json()["odontologicos"], r.json()["rechazados"]) == (9, 5, 0)
    assert db.execute(text("SELECT count(*) FROM cie10 WHERE es_odontologico")).scalar_one() == 5
    otra = _subir(admin, archivos[0], "catalogo-cie10")
    assert otra.status_code == 409 and "una sola vez" in otra.json()["detail"]


def test_catalogo_solo_filas_marcadas(admin, archivos, db):
    r = _subir(admin, archivos[0], "catalogo-cie10", solo_filas_marcadas="true")
    assert r.status_code == 201 and r.json()["odontologicos"] == 5


def test_atenciones_sin_catalogo_422_y_con_catalogo_crea_todo(admin, archivos, db):
    sin = _subir(admin, archivos[1], "atenciones")
    assert sin.status_code == 422 and "catálogo" in sin.json()["detail"].lower()
    _subir(admin, archivos[0], "catalogo-cie10")
    r = _subir(admin, archivos[1], "atenciones")
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["insertados"] > 0 and cuerpo["pacientes_nuevos"] > 0
    assert db.execute(text("SELECT count(*) FROM paciente")).scalar_one() == cuerpo["pacientes_nuevos"]
    repetida = _subir(admin, archivos[1], "atenciones").json()
    assert (
        repetida["insertados"] == 0 and repetida["omitidos"] == cuerpo["insertados"] + cuerpo["omitidos"]
    )  # no duplica


def test_cola_de_revision_historial_y_resolver_fila(admin, archivos):
    _subir(admin, archivos[0], "catalogo-cie10")
    id_imp = _subir(admin, archivos[1], "atenciones").json()["id_importacion"]
    hist = admin.get(RUTA).json()
    assert hist["total"] == 2 and hist["items"][0]["id_importacion"] == id_imp
    assert admin.get(f"{RUTA}/{id_imp}").json()["tipo"] == "atenciones"
    filas = admin.get(f"{RUTA}/{id_imp}/filas").json()
    assert filas["total"] >= 2 and filas["items"][0]["motivo"] and isinstance(filas["items"][0]["datos"], dict)
    id_fila = filas["items"][0]["id_fila"]
    assert admin.patch(f"{RUTA}/{id_imp}/filas/{id_fila}", json={"estado": "resuelta"}).json()["estado"] == "resuelta"
    assert admin.get(f"{RUTA}/{id_imp}/filas", params={"estado": "resuelta"}).json()["total"] == 1
    assert admin.patch(f"{RUTA}/{id_imp}/filas/{id_fila}", json={"estado": "otra"}).status_code == 422
    assert admin.patch(f"{RUTA}/{id_imp}/filas/999999", json={"estado": "resuelta"}).status_code == 404
    assert admin.get(f"{RUTA}/999999").status_code == 404
    assert admin.get(f"{RUTA}/999999/filas").status_code == 404


def test_archivos_invalidos(admin, tmp_path, archivos):
    mal = tmp_path / "x.txt"
    mal.write_text("hola")
    assert _subir(admin, mal, "catalogo-cie10", tipo="text/plain").status_code == 415
    falso = tmp_path / "falso.xlsx"
    falso.write_bytes(b"esto no es un excel")
    assert _subir(admin, falso, "catalogo-cie10").status_code == 415
    vacio = tmp_path / "vacio.csv"
    vacio.write_bytes(b"")
    assert _subir(admin, vacio, "atenciones", tipo="text/csv").status_code == 422
    sin_estructura = tmp_path / "otro.csv"
    sin_estructura.write_text("a,b\n1,2\n")
    assert _subir(admin, sin_estructura, "catalogo-cie10", tipo="text/csv").status_code == 422
    assert admin.post(f"{RUTA}/atenciones").status_code == 422  # sin archivo


def test_archivo_demasiado_grande(admin, archivos, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("MAX_IMPORT_MB", "0")
    get_settings.cache_clear()
    try:
        assert _subir(admin, archivos[0], "catalogo-cie10").status_code == 413
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_solo_administrador(client, archivos):
    assert client.get(RUTA).status_code == 403
    assert _subir(client, archivos[0], "catalogo-cie10").status_code == 403
    assert _subir(client, archivos[1], "atenciones").status_code == 403


def test_importaciones_quedan_auditadas(admin, archivos, db):
    _subir(admin, archivos[0], "catalogo-cie10")
    admin.get(RUTA)
    acciones = [a for (a,) in db.execute(text("SELECT accion FROM auditoria ORDER BY id_evento"))]
    assert acciones == ["importar_catalogo_cie10", "consultar_importaciones"]


# --- imágenes en lote -----------------------------------------------------------------------------------------


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path / "alm", "t" * 40, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a
    return a


def _lote(client, id_paciente, archivos, **extra):
    return client.post(
        "/api/v1/imagenes/lote",
        data={"id_paciente": str(id_paciente), **extra},
        files=[("archivos", (n, c, "image/jpeg")) for n, c in archivos],
    )


def test_lote_sube_las_validas_y_reporta_las_fallidas(client, seed, almacen):
    maria = seed["maria"].public_id
    r = _lote(client, maria, [("a.jpg", JPEG), ("b.jpg", JPEG + b"1"), ("c.jpg", JPEG), ("malo.jpg", b"no es imagen")])
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["total"], d["subidas"], d["fallidas"]) == (4, 2, 2)  # c.jpg es duplicado de a.jpg
    errores = {x["nombre_archivo"]: x["error"] for x in d["resultados"] if x["error"]}
    assert "ya está cargada" in errores["c.jpg"] and "JPEG" in errores["malo.jpg"]
    assert client.get("/api/v1/imagenes", params={"id_paciente": str(maria)}).json()["total"] == 2


def test_lote_errores_globales(client, seed, almacen, monkeypatch):
    assert _lote(client, "00000000-0000-0000-0000-000000000000", [("a.jpg", JPEG)]).status_code == 404
    maria = seed["maria"].public_id
    assert (
        _lote(client, maria, [("a.jpg", JPEG)], id_atencion="00000000-0000-0000-0000-000000000000").status_code == 422
    )
    from app.core.config import get_settings

    monkeypatch.setenv("MAX_IMPORT_IMAGES", "1")
    get_settings.cache_clear()
    try:
        assert _lote(client, maria, [("a.jpg", JPEG), ("b.jpg", JPEG + b"1")]).status_code == 413
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
