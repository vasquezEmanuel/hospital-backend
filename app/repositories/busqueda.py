"""Búsqueda de texto sin distinguir tildes ni mayúsculas. Carpeta: app/repositories — Sprint 1 (corrección).

Quien busca escribe "maria" y espera encontrar "María". Se usa translate() de PostgreSQL (nativo: no requiere
extensiones ni cambios de esquema) sobre la columna, y la misma normalización sobre el texto buscado.
"""

import unicodedata

from sqlalchemy import func

_CON_TILDE = "áéíóúüñÁÉÍÓÚÜÑ"
_SIN_TILDE = "aeiouunAEIOUUN"


def sin_tildes(columna):
    """Expresión SQL: la columna en minúsculas y sin tildes (ñ cuenta como n)."""
    return func.lower(func.translate(columna, _CON_TILDE, _SIN_TILDE))


def normalizar_busqueda(texto: str) -> str:
    """Mismo tratamiento que sin_tildes(), aplicado al texto que escribió el usuario."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()