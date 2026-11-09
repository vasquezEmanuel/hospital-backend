"""CORS: el front (otro dominio) solo puede llamar a la API si su origen está en CORS_ORIGINS. Carpeta: tests/.

Corresponde a la configuración de seguridad del Sprint 5 (Fase G) y a la conexión del front con el backend.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.config import Settings

FRONT = "https://front.hospital.example"


def _cliente(monkeypatch, origenes: str) -> TestClient:
    monkeypatch.setattr(main, "get_settings", lambda: Settings(cors_origins=origenes))
    return TestClient(main.create_app())


def _preflight(c: TestClient, origen: str, metodo: str = "POST"):
    return c.options(
        "/api/v1/pacientes",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": metodo,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_origen_permitido_recibe_los_permisos(monkeypatch):
    r = _preflight(_cliente(monkeypatch, FRONT), FRONT)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == FRONT
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert r.headers["access-control-max-age"] == "600"


def test_origen_no_listado_es_rechazado(monkeypatch):
    r = _preflight(_cliente(monkeypatch, FRONT), "https://intruso.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_barra_final_en_la_variable_no_rompe_el_cors(monkeypatch):
    r = _preflight(_cliente(monkeypatch, FRONT + "/"), FRONT)
    assert r.headers["access-control-allow-origin"] == FRONT


def test_varios_origenes_separados_por_coma(monkeypatch):
    c = _cliente(monkeypatch, f"{FRONT}, http://localhost:5173")
    assert _preflight(c, "http://localhost:5173").headers["access-control-allow-origin"] == "http://localhost:5173"
    assert _preflight(c, FRONT).headers["access-control-allow-origin"] == FRONT


def test_sin_origenes_configurados_no_hay_cors(monkeypatch):
    assert "access-control-allow-origin" not in _preflight(_cliente(monkeypatch, ""), FRONT).headers


def test_no_se_permiten_cookies_entre_dominios(monkeypatch):
    assert "access-control-allow-credentials" not in _preflight(_cliente(monkeypatch, FRONT), FRONT).headers


def test_respuesta_de_error_tambien_lleva_cors(monkeypatch):
    """Si no, el front vería un error de CORS en vez del 401 real."""
    r = _cliente(monkeypatch, FRONT).get("/api/v1/pacientes", headers={"Origin": FRONT})
    assert r.status_code == 401 and r.headers["access-control-allow-origin"] == FRONT


@pytest.mark.parametrize("origen", ["http://localhost:5173", "http://front.hospital.example"])
def test_produccion_rechaza_origenes_http(origen):
    s = Settings(cors_origins=origen)
    assert any("https://" in p for p in s.problemas_produccion())
