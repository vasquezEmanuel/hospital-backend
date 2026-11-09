"""Sprint 5: tokens del proveedor de identidad (claves públicas), MFA y configuración de producción."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import security
from app.core.config import Settings
from app.core.security import get_current_user
from app.main import create_app

ISSUER = "https://proyecto.supabase.co/auth/v1"


@pytest.fixture(scope="module")
def llave():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def servidor_jwks(llave):
    """Servidor HTTP local que publica las claves como lo hace Supabase en /auth/v1/.well-known/jwks.json."""
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(llave.public_key()))
    jwk.update(kid="clave-1", alg="ES256", use="sig")
    cuerpo = json.dumps({"keys": [jwk]}).encode()

    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nombre exigido por http.server)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    security._jwks_client.cache_clear()
    yield f"http://127.0.0.1:{servidor.server_port}/jwks.json"
    servidor.shutdown()
    security._jwks_client.cache_clear()


def _ajustes(url_jwks, **extra):
    base = dict(
        _env_file=None,
        auth_jwks_url=url_jwks,
        auth_issuer=ISSUER,
        auth_audience="authenticated",
        auth_algorithms="ES256,HS256",  # HS256 a propósito: debe ignorarse al haber JWKS
        auth_roles_claim="app_metadata.roles",
    )
    return Settings(**{**base, **extra})


def _token(llave, **claims):
    carga = {
        "sub": "uuid-1",
        "email": "dra@hospital.test",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": 4102444800,
        "aal": "aal1",
        "app_metadata": {"roles": ["odontologo"]},
    }
    carga.update(claims)
    return jwt.encode(carga, llave, "ES256", headers={"kid": "clave-1"})


def _usuario(token, ajustes):
    return get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), ajustes)


def test_token_es256_de_supabase_se_valida_con_las_claves_publicas(llave, servidor_jwks):
    usuario = _usuario(_token(llave), _ajustes(servidor_jwks))
    assert usuario.sub == "uuid-1" and usuario.roles == {"odontologo"} and usuario.aal == "aal1"


@pytest.mark.parametrize(
    "cambio",
    [{"aud": "otra-app"}, {"iss": "https://otro.example/auth/v1"}, {"exp": 1}],
    ids=["audiencia", "emisor", "vencido"],
)
def test_token_con_audiencia_emisor_o_vencimiento_incorrecto_es_401(llave, servidor_jwks, cambio):
    with pytest.raises(HTTPException) as e:
        _usuario(_token(llave, **cambio), _ajustes(servidor_jwks))
    assert e.value.status_code == 401


def test_con_jwks_un_token_hs256_se_rechaza_aunque_este_permitido(servidor_jwks):
    falso = jwt.encode(
        {"sub": "x", "aud": "authenticated", "iss": ISSUER, "exp": 4102444800}, "secreto-conocido-" * 3, "HS256"
    )
    with pytest.raises(HTTPException) as e:
        _usuario(falso, _ajustes(servidor_jwks, auth_jwt_secret="secreto-conocido-" * 3))
    assert e.value.status_code == 401


def test_con_jwks_y_solo_hs256_configurado_falla_cerrado(llave, servidor_jwks):
    with pytest.raises(HTTPException) as e:
        _usuario(_token(llave), _ajustes(servidor_jwks, auth_algorithms="HS256"))
    assert e.value.status_code == 401


@pytest.mark.parametrize("aal, entra", [("aal2", True), ("aal1", False), (None, False)])
def test_con_mfa_obligatorio_solo_entra_el_segundo_factor_verificado(llave, servidor_jwks, aal, entra):
    token = _token(llave, **({"aal": aal} if aal else {}))
    if not aal:
        carga = jwt.decode(token, options={"verify_signature": False})
        carga.pop("aal", None)
        token = jwt.encode(carga, llave, "ES256", headers={"kid": "clave-1"})
    ajustes = _ajustes(servidor_jwks, auth_require_mfa=True)
    if entra:
        assert _usuario(token, ajustes).aal == "aal2"
    else:
        with pytest.raises(HTTPException) as e:
            _usuario(token, ajustes)
        assert e.value.status_code == 403 and "MFA" in e.value.detail


def test_sin_mfa_obligatorio_basta_el_primer_factor(llave, servidor_jwks):
    assert _usuario(_token(llave, aal="aal1"), _ajustes(servidor_jwks)).roles == {"odontologo"}


def _produccion(**cambios):
    base = dict(
        _env_file=None,
        environment="production",
        docs_enabled=False,
        auth_jwks_url="https://p.supabase.co/auth/v1/.well-known/jwks.json",
        auth_issuer=ISSUER,
        auth_audience="authenticated",
        auth_require_mfa=True,
        storage_backend="s3",
        cors_origins="https://app.hospital.example",
    )
    return Settings(**{**base, **cambios})


def test_produccion_bien_configurada_no_tiene_problemas():
    assert _produccion().problemas_produccion() == []


@pytest.mark.parametrize(
    "cambio, texto",
    [
        ({"docs_enabled": True}, "DOCS_ENABLED"),
        ({"auth_jwks_url": ""}, "AUTH_JWKS_URL"),
        ({"auth_issuer": ""}, "AUTH_ISSUER"),
        ({"auth_audience": ""}, "AUTH_AUDIENCE"),
        ({"storage_backend": "local"}, "STORAGE_BACKEND"),
        ({"cors_origins": ""}, "CORS_ORIGINS"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
    ],
)
def test_produccion_insegura_se_detecta(cambio, texto):
    assert any(texto in p for p in _produccion(**cambio).problemas_produccion())


def test_la_app_no_arranca_en_produccion_con_configuracion_insegura(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: _produccion(docs_enabled=True))
    with pytest.raises(RuntimeError, match="Configuración insegura"):
        create_app()
    monkeypatch.setattr("app.main.get_settings", lambda: _produccion())
    assert create_app().title


def test_produccion_no_exige_mfa_por_decision_del_equipo():
    """El segundo factor es opcional (AUTH_REQUIRE_MFA): su ausencia no impide arrancar en producción."""
    assert _produccion(auth_require_mfa=False).problemas_produccion() == []
