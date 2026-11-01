"""Normalización de valores de las fuentes. Carpeta: etl/ — Sprint 2, Fase 3 del documento técnico.

Funciones puras (sin BD, sin archivos): reciben el valor crudo de una celda y devuelven el valor limpio.
Regla 1 del prompt: el documento de identidad se normaliza con la MISMA función que usa la API.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta

from app.schemas.paciente import normalizar_documento  # una sola regla para API y ETL

__all__ = ["clave_texto", "limpiar_codigo_cie10", "normalizar_documento", "parsear_fecha", "vacio"]

_ESPACIOS = re.compile(r"\s+")
_EPOCA_EXCEL = datetime(1899, 12, 30)  # sistema de fechas 1900 de Excel
_SERIAL_MIN, _SERIAL_MAX = 36526, 73051  # 2000-01-01 .. 2099-12-31
_FORMATOS_FECHA = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y")


def vacio(valor) -> bool:
    """True si la celda no trae dato (None, texto en blanco). Un 0 o un False NO son vacío."""
    return valor is None or (isinstance(valor, str) and not valor.strip())


def clave_texto(valor: str) -> str:
    """Clave de comparación: sin tildes, mayúsculas, espacios colapsados. 'Nueva  EPS' == 'NUEVA EPS'.

    Se usa para emparejar aseguradora, profesional y ubicación contra los catálogos de la BD.
    """
    sin_tildes = unicodedata.normalize("NFD", str(valor))
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return _ESPACIOS.sub(" ", sin_tildes).strip().upper()


def limpiar_codigo_cie10(valor: str) -> str:
    """'k02.1 ' -> 'K021'; 'A065†' -> 'A065'. cie10.cod_4 se guarda sin punto, sin †/* y en mayúsculas.

    El catálogo oficial marca con † o * los códigos de doble clasificación; no forman parte del código.
    """
    return re.sub(r"[.\s†‡*]", "", str(valor)).upper()


def parsear_fecha(valor) -> date:
    """Acepta date/datetime, número de serie de Excel o texto DD/MM/AAAA | AAAA-MM-DD. Lanza ValueError si no."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, int | float) and not isinstance(valor, bool) and _SERIAL_MIN <= valor <= _SERIAL_MAX:
        return (_EPOCA_EXCEL + timedelta(days=int(valor))).date()  # número de serie de Excel sin formato de fecha
    texto = str(valor).strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {valor!r}")
