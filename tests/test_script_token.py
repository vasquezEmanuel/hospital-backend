"""Prueba del generador de tokens de desarrollo: el token debe ser aceptado por la validación real de la API."""

import pytest

from app.core.config import Settings
from app.core.security import decode_token
from scripts.generar_token import crear_token

SECRETO = "x" * 40


def test_token_generado_pasa_la_validacion_de_la_api():
    s = Settings(auth_jwt_secret=SECRETO)
    claims = decode_token(crear_token(s, rol="administrador", sub="ana"), s)
    assert claims["sub"] == "ana" and claims["groups"] == ["administrador"]


def test_respeta_la_ruta_de_roles_configurada():
    s = Settings(auth_jwt_secret=SECRETO, auth_roles_claim="app_metadata.roles")
    assert decode_token(crear_token(s), s)["app_metadata"]["roles"] == ["odontologo"]


def test_exige_un_secreto_largo():
    with pytest.raises(SystemExit):
        crear_token(Settings(auth_jwt_secret="corto"))


def test_no_emite_tokens_en_produccion():
    with pytest.raises(SystemExit, match="solo para desarrollo"):
        crear_token(Settings(auth_jwt_secret=SECRETO, environment="production"))
