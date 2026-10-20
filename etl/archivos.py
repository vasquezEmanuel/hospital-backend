"""Lectura de tablas desde XLSX o CSV. Carpeta: etl/ — Sprint 2, Fase 3 (extracción)."""

import csv
import io
from pathlib import Path

from openpyxl import load_workbook

from etl.comunes import ErrorFormato


def texto(valor) -> str:
    """Celda -> texto limpio y en una línea. Excel entrega números como float: 1025847210.0 -> '1025847210'."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return " ".join(str(valor).split())


def texto_libre(valor) -> str:
    """Como texto(), pero conserva los saltos de línea (plan de tratamiento, observaciones)."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def leer_tabla(ruta, con_celdas: bool = False):
    """Devuelve (filas, celdas).

    filas: lista de listas con los valores. celdas: las celdas de openpyxl (solo XLSX y con_celdas=True), necesarias
    cuando importa el formato, p. ej. el subrayado que marca los códigos odontológicos. None en los demás casos.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    sufijo = ruta.suffix.lower()
    if sufijo in (".xlsx", ".xlsm"):
        return _leer_xlsx(ruta, con_celdas)
    if sufijo == ".csv":
        return _leer_csv(ruta), None
    raise ErrorFormato(f"Formato no soportado: {ruta.suffix or '(sin extensión)'}. Use XLSX o CSV.")


def _leer_xlsx(ruta: Path, con_celdas: bool):
    try:
        libro = load_workbook(ruta, read_only=not con_celdas, data_only=True)
    except Exception as exc:  # archivo corrupto, extensión falsa, etc.
        raise ErrorFormato(f"No se pudo abrir el Excel: {exc}") from exc
    try:
        hoja = libro.worksheets[0]
        if con_celdas:
            celdas = [list(fila) for fila in hoja.iter_rows()]
            return [[c.value for c in fila] for fila in celdas], celdas
        return [list(fila) for fila in hoja.iter_rows(values_only=True)], None
    finally:
        libro.close()


def _leer_csv(ruta: Path) -> list[list[str]]:
    crudo = ruta.read_bytes()
    try:
        contenido = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:  # CSV exportado por Excel en Windows
        contenido = crudo.decode("latin-1")
    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    return list(csv.reader(io.StringIO(contenido), dialecto))