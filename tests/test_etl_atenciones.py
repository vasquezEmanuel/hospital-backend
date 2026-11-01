"""Pruebas del lector de la hoja de atenciones (no necesitan base de datos)."""

from datetime import date

import pytest
import xlwt
from openpyxl import Workbook

from etl.archivos import texto
from etl.comunes import ErrorFormato
from etl.lector_atenciones import leer_atenciones
from scripts.generar_datos_demo import crear_atenciones_demo


def _xlsx(ruta, filas):
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)
    return ruta


def test_hoja_demo_separa_filas_validas_y_rechazadas(tmp_path):
    lectura = leer_atenciones(crear_atenciones_demo(tmp_path / "a.xlsx"))
    assert len(lectura.filas) == 10
    assert {r.numero_fila for r in lectura.rechazos} == {9, 10}  # documento "12" y fecha "ayer"
    motivos = " | ".join(r.motivo for r in lectura.rechazos)
    assert "Documento de identidad inválido" in motivos and "Fecha de la atención no reconocida" in motivos


def test_normaliza_documento_fecha_y_textos(tmp_path):
    filas = leer_atenciones(crear_atenciones_demo(tmp_path / "a.xlsx")).filas
    maria = filas[0]
    assert maria.documento == "1025847210" and maria.fecha == date(2026, 9, 12)
    assert maria.dx_hospitalario == "C187"
    assert maria.dx_bucales == [(1, "K021"), (2, "Gingivitis aguda")]  # la columna 3 está vacía
    carlos = filas[1]  # documento numérico en la celda y fecha en texto DD/MM/AAAA
    assert carlos.documento == "79421880" and carlos.fecha == date(2026, 9, 11)
    segundo_carlos = filas[6]  # la fila 6 es la repetida de María; la 7 trae espacios de más
    assert segundo_carlos.nombre == "Carlos Gómez" and segundo_carlos.aseguradora == "sura"


def test_numeros_de_excel_como_float_no_agregan_cero():
    assert texto(1025847210.0) == "1025847210"
    assert texto(3.5) == "3.5"


def test_encabezados_sin_tildes_ni_mayusculas(tmp_path):
    ruta = _xlsx(
        tmp_path / "a.xlsx",
        [
            ["Fecha de la Atencion", "documento de identidad", "Nombre", "diagnostico bucal 2"],
            ["2026-09-12", "123456", "Ana Pérez", "K021"],
        ],
    )
    (fila,) = leer_atenciones(ruta).filas
    assert fila.dx_bucales == [(2, "K021")] and fila.aseguradora is None


def test_faltan_columnas_obligatorias(tmp_path):
    ruta = _xlsx(tmp_path / "a.xlsx", [["FECHA DE LA ATENCIÓN", "DOCUMENTO DE IDENTIDAD"], ["2026-09-12", "123456"]])
    with pytest.raises(ErrorFormato, match="NOMBRE"):
        leer_atenciones(ruta)


def test_sin_encabezado_reconocible(tmp_path):
    ruta = _xlsx(tmp_path / "a.xlsx", [["a", "b"], [1, 2]])
    with pytest.raises(ErrorFormato, match="encabezado"):
        leer_atenciones(ruta)


def test_nombre_demasiado_largo_va_a_rechazos(tmp_path):
    ruta = _xlsx(
        tmp_path / "a.xlsx",
        [["FECHA", "DOCUMENTO", "NOMBRE"], ["2026-09-12", "123456", "N" * 151]],
    )
    lectura = leer_atenciones(ruta)
    assert not lectura.filas and "supera 150" in lectura.rechazos[0].motivo


def test_csv_con_punto_y_coma(tmp_path):
    ruta = tmp_path / "a.csv"
    ruta.write_text(
        "FECHA DE LA ATENCIÓN;DOCUMENTO DE IDENTIDAD;NOMBRE;DIAGNÓSTICO BUCAL 1\n12/09/2026;1.025.847.210;María;K021\n",
        encoding="utf-8",
    )
    (fila,) = leer_atenciones(ruta).filas
    assert fila.documento == "1025847210" and fila.dx_bucales == [(1, "K021")]


def test_xls_con_fechas_de_excel_y_diagnosticos_en_texto_libre(tmp_path):
    ruta = tmp_path / "a.xls"
    libro = xlwt.Workbook()
    hoja = libro.add_sheet("Hoja1")
    for j, h in enumerate(["FECHA DE LA ATENCIÓN", " NOMBRE", "DOCUMENTO DE IDENTIDAD", "DIAGNÓSTICO BUCAL 1"]):
        hoja.write(0, j, h)
    hoja.write(1, 0, date(2026, 9, 12), xlwt.easyxf(num_format_str="DD/MM/YYYY"))  # celda de tipo fecha
    hoja.write(1, 1, "Ana Pérez")
    hoja.write(1, 2, 1025847210)  # número, no texto
    hoja.write(1, 3, "CARIES")
    hoja.write(2, 0, 46277)  # número de serie sin formato de fecha
    hoja.write(2, 1, "Luis Gómez")
    hoja.write(2, 2, "79421880")
    libro.save(str(ruta))
    ana, luis = leer_atenciones(ruta).filas
    assert (ana.fecha, ana.documento, ana.dx_bucales) == (date(2026, 9, 12), "1025847210", [(1, "CARIES")])
    assert (luis.fecha, luis.documento) == (date(2026, 9, 12), "79421880")
