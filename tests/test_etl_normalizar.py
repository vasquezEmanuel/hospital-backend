"""Pruebas de etl/normalizar.py (no necesitan base de datos)."""

from datetime import date, datetime

import pytest

from etl.normalizar import clave_texto, limpiar_codigo_cie10, normalizar_documento, parsear_fecha, vacio


def test_vacio():
    assert vacio(None) and vacio("") and vacio("   ")
    assert not vacio("x") and not vacio(0)


def test_clave_texto_ignora_tildes_mayusculas_y_espacios():
    assert clave_texto("  Nueva   EPS ") == "NUEVA EPS"
    assert clave_texto("Dra. Laura Castaño") == "DRA. LAURA CASTANO"


def test_limpiar_codigo_cie10():
    assert limpiar_codigo_cie10(" k02.1 ") == "K021"
    assert limpiar_codigo_cie10("C187") == "C187"


def test_documento_usa_la_misma_regla_que_la_api():
    assert normalizar_documento("1.025.847.210") == "1025847210"
    with pytest.raises(ValueError):
        normalizar_documento("12")


@pytest.mark.parametrize(
    "valor",
    [date(2026, 9, 12), datetime(2026, 9, 12, 9, 30), "12/09/2026", "2026-09-12", " 12-09-2026 "],
)
def test_parsear_fecha_formatos_validos(valor):
    assert parsear_fecha(valor) == date(2026, 9, 12)


def test_parsear_fecha_invalida():
    with pytest.raises(ValueError):
        parsear_fecha("31/02/2026")
    with pytest.raises(ValueError):
        parsear_fecha("ayer")