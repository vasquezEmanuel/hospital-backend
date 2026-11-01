"""Lectura de tablas desde XLS, XLSX o CSV. Carpeta: etl/ — Sprint 2, Fase 3 (extracción).

El hospital entrega sus archivos en Excel antiguo (.xls): por eso se lee con xlrd. Los .xlsx se leen con openpyxl y los
CSV con el módulo estándar. Cuando importa el FORMATO de una celda (subrayado o relleno de color: así marca el hospital
los códigos odontológicos) se pide con con_formato=True.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import xlrd
from openpyxl import load_workbook

from etl.comunes import ErrorFormato

_SIN_RELLENO_XLS = {0, 9, 64, 65, 0x7FFF}  # sin color, blanco y "automático"
_SIN_RELLENO_XLSX = {"FFFFFF", "000000"}


@dataclass(frozen=True)
class FormatoCelda:
    subrayada: bool = False
    resaltada: bool = False  # relleno de color distinto de blanco

    @property
    def marcada(self) -> bool:
        return self.subrayada or self.resaltada


# formato(fila, columna) con índices base 0. None si el archivo no conserva formato (CSV) o no se pidió.
FuncionFormato = Callable[[int, int], FormatoCelda]


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


def leer_tabla(ruta, con_formato: bool = False) -> tuple[list[list], FuncionFormato | None]:
    """Devuelve (filas, formato). filas: lista de listas con los valores de la primera hoja."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    sufijo = ruta.suffix.lower()
    if sufijo == ".xls":
        return _leer_xls(ruta, con_formato)
    if sufijo in (".xlsx", ".xlsm"):
        return _leer_xlsx(ruta, con_formato)
    if sufijo == ".csv":
        return _leer_csv(ruta), None
    raise ErrorFormato(f"Formato no soportado: {ruta.suffix or '(sin extensión)'}. Use XLS, XLSX o CSV.")


# ---------------------------------------------------------------- .xls (Excel 97-2003)


def _valor_xls(celda, modo_fechas: int):
    tipo = celda.ctype
    if tipo in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return None
    if tipo == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate_as_datetime(celda.value, modo_fechas)
        except xlrd.XLDateError:
            return celda.value
    if tipo == xlrd.XL_CELL_BOOLEAN:
        return bool(celda.value)
    return celda.value


def _leer_xls(ruta: Path, con_formato: bool):
    try:
        libro = xlrd.open_workbook(str(ruta), formatting_info=con_formato)
    except Exception as exc:  # archivo corrupto, extensión falsa, etc.
        raise ErrorFormato(f"No se pudo abrir el Excel: {exc}") from exc
    hoja = libro.sheet_by_index(0)
    filas = []
    for i in range(hoja.nrows):
        celdas = hoja.row(i)
        while celdas and celdas[-1].ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
            celdas = celdas[:-1]  # las hojas .xls traen 256 columnas: se descartan las vacías del final
        filas.append([_valor_xls(c, libro.datemode) for c in celdas])
    if not con_formato:
        return filas, None

    def formato(i: int, j: int) -> FormatoCelda:
        try:
            xf = libro.xf_list[hoja.cell_xf_index(i, j)]
        except IndexError:
            return FormatoCelda()
        fondo = xf.background
        resaltada = fondo.fill_pattern != 0 and fondo.pattern_colour_index not in _SIN_RELLENO_XLS
        return FormatoCelda(subrayada=bool(libro.font_list[xf.font_index].underline_type), resaltada=resaltada)

    return filas, formato


# ---------------------------------------------------------------- .xlsx


def _color_resalta(color) -> bool:
    if color is None:
        return False
    if color.type == "rgb":
        return str(color.rgb).upper()[-6:] not in _SIN_RELLENO_XLSX
    if color.type == "indexed":
        return color.indexed not in _SIN_RELLENO_XLS
    if color.type == "theme":
        return not (color.theme == 0 and not color.tint)  # tema 0 = blanco
    return False


def _leer_xlsx(ruta: Path, con_formato: bool):
    try:
        libro = load_workbook(ruta, read_only=not con_formato, data_only=True)
    except Exception as exc:  # archivo corrupto, extensión falsa, etc.
        raise ErrorFormato(f"No se pudo abrir el Excel: {exc}") from exc
    try:
        hoja = libro.worksheets[0]
        if not con_formato:
            return [list(fila) for fila in hoja.iter_rows(values_only=True)], None
        celdas = [list(fila) for fila in hoja.iter_rows()]
    finally:
        libro.close()

    def formato(i: int, j: int) -> FormatoCelda:
        if i >= len(celdas) or j >= len(celdas[i]):
            return FormatoCelda()
        celda = celdas[i][j]
        relleno = celda.fill
        resaltada = relleno is not None and relleno.fill_type == "solid" and _color_resalta(relleno.fgColor)
        return FormatoCelda(subrayada=bool(celda.font and celda.font.u), resaltada=bool(resaltada))

    return [[c.value for c in fila] for fila in celdas], formato


# ---------------------------------------------------------------- .csv


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
