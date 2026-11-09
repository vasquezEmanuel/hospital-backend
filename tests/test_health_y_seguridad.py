import jwt

from app.core.config import Settings
from app.core.security import decode_token


def test_health_sin_autenticacion(anon_client):
    body = anon_client.get("/health").json()
    assert body["status"] == "ok" and "commit" in body


def test_ready_toca_la_bd(client):
    assert client.get("/health/ready").status_code == 200


def test_endpoints_clinicos_exigen_token(anon_client):
    assert anon_client.get("/api/v1/pacientes").status_code == 401
    assert anon_client.get("/api/v1/cie10").status_code == 401


def test_token_invalido_es_401(anon_client):
    r = anon_client.get("/api/v1/pacientes", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401


def test_rol_insuficiente_es_403(client):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="x", roles=frozenset(["visitante"]))
    assert client.get("/api/v1/pacientes").status_code == 403


def test_decode_token_hs256_y_ruta_de_roles():
    s = Settings(auth_jwt_secret="s" * 40, auth_roles_claim="app_metadata.roles")
    tok = jwt.encode({"sub": "u1", "exp": 4102444800, "app_metadata": {"roles": ["odontologo"]}}, "s" * 40, "HS256")
    assert decode_token(tok, s)["sub"] == "u1"


def test_ready_registra_la_causa_cuando_la_bd_falla(client, caplog):
    """Si la BD no responde, el cliente recibe 503 y el log de Render dice por qué (usuario, contraseña, red...)."""
    from sqlalchemy.exc import OperationalError

    from app.db.session import get_db
    from app.main import app

    class _Caida:
        def execute(self, *_):
            raise OperationalError(
                "SELECT 1", {}, Exception('FATAL: password authentication failed for user "hospital_api"')
            )

    app.dependency_overrides[get_db] = lambda: _Caida()
    try:
        with caplog.at_level("ERROR", logger="uvicorn.error"):
            r = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503 and r.json()["detail"] == "Base de datos no disponible"
    assert "password authentication failed" in caplog.text
