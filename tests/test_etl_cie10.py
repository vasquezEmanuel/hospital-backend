"""Pruebas del lector del catálogo CIE-10 (no necesitan base de datos)."""

import pytest
import xlwt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from etl.comunes import ErrorFormato
from etl.lector_cie10 import leer_catalogo
from scripts.generar_datos_demo import crear_catalogo_demo


def _xlsx(ruta, filas, subrayadas=()):
    """Crea un XLSX. subrayadas: pares (fila, columna) base 1 que llevan la fuente subrayada."""
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    for r, c in subrayadas:
        hoja.cell(row=r, column=c).font = Font(underline="single")
    libro.save(ruta)
    return ruta


def test_catalogo_demo_marca_odontologicos_por_subrayado(tmp_path):
    lectura = leer_catalogo(crear_catalogo_demo(tmp_path / "c.xlsx"))
    assert len(lectura.filas) == 9 and not lectura.rechazos
    odontologicos = {f.cod_4 for f in lectura.filas if f.es_odontologico}
    assert odontologicos == {"K021", "K050", "K051", "K083", "K123"}
    k021 = next(f for f in lectura.filas if f.cod_4 == "K021")
    assert (k021.cod_3, k021.descripcion_3, k021.descripcion_4) == ("K02", "Caries dental", "Caries de la dentina")


def test_columnas_en_otro_orden_y_subrayado_en_la_descripcion(tmp_path):
    ruta = _xlsx(
        tmp_path / "c.xlsx",
        [
            ["Catálogo CIE-10 (título)"],  # el encabezado no está en la primera fila
            ["COD_3", "COD_4", "DESCRIPCION 3", "DESCRIPCION 4"],
            ["K02", "k02.1", "Caries dental", "Caries de la dentina"],
            ["C18", "C187", "Tumor maligno del colon", "Tumor maligno del colon sigmoide"],
        ],
        subrayadas=[(3, 4)],  # subrayada la descripción, no el código
    )
    filas = {f.cod_4: f for f in leer_catalogo(ruta).filas}
    assert filas["K021"].es_odontologico and not filas["C187"].es_odontologico
    assert filas["K021"].descripcion_3 == "Caries dental"
    assert filas["C187"].descripcion_4 == "Tumor maligno del colon sigmoide"


def test_csv_con_columna_es_odontologico_punto_y_coma_y_latin1(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_bytes(
        (
            "COD_3;DESCRIPCION;COD_4;DESCRIPCION;ES_ODONTOLOGICO\n"
            "K05;Gingivitis;K051;Gingivitis crónica;SI\n"
            "C18;Tumor;C187;Tumor maligno del colon sigmoide;NO\n"
        ).encode("latin-1")
    )
    filas = {f.cod_4: f for f in leer_catalogo(ruta).filas}
    assert filas["K051"].es_odontologico and filas["K051"].descripcion_4 == "Gingivitis crónica"
    assert not filas["C187"].es_odontologico


def test_csv_sin_columna_es_odontologico_se_rechaza(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_text("COD_4,DESCRIPCION\nK021,Caries de la dentina\n", encoding="utf-8")
    with pytest.raises(ErrorFormato, match="ES_ODONTOLOGICO"):
        leer_catalogo(ruta)


def test_xlsx_sin_ningun_subrayado_se_rechaza(tmp_path):
    ruta = _xlsx(tmp_path / "c.xlsx", [["COD_4", "DESCRIPCION"], ["K021", "Caries de la dentina"]])
    with pytest.raises(ErrorFormato, match="subrayada"):
        leer_catalogo(ruta)


def test_filas_invalidas_van_a_rechazos_con_su_numero(tmp_path):
    ruta = _xlsx(
        tmp_path / "c.xlsx",
        [
            ["COD_4", "DESCRIPCION"],
            ["K021", "Caries de la dentina"],  # fila 2: válida y subrayada
            ["12", "Código malo"],  # fila 3
            [None, "Sin código"],  # fila 4
            ["K050", None],  # fila 5
            ["K021", "Repetida"],  # fila 6
        ],
        subrayadas=[(2, 1)],
    )
    lectura = leer_catalogo(ruta)
    assert [f.cod_4 for f in lectura.filas] == ["K021"]
    assert {r.numero_fila: r.motivo for r in lectura.rechazos} == {
        3: "COD_4 con formato inválido: '12'",
        4: "Fila sin COD_4",
        5: "El código K050 no tiene descripción",
        6: "COD_4 K021 repetido en el archivo: se conserva la primera aparición",
    }


def test_formatos_no_soportados(tmp_path):
    (tmp_path / "c.txt").write_text("x")
    with pytest.raises(ErrorFormato, match="no soportado"):
        leer_catalogo(tmp_path / "c.txt")
    with pytest.raises(FileNotFoundError):
        leer_catalogo(tmp_path / "no_existe.xlsx")
    falso = tmp_path / "falso.xlsx"
    falso.write_text("esto no es un excel")
    with pytest.raises(ErrorFormato, match="No se pudo abrir"):
        leer_catalogo(falso)


def _xls(ruta, filas, resaltadas=()):
    """Crea un .xls (Excel 97-2003, el formato real del hospital). resaltadas: filas (base 1) con relleno amarillo."""
    libro = xlwt.Workbook()
    hoja = libro.add_sheet("Hoja1")
    amarillo = xlwt.easyxf("pattern: pattern solid, fore_colour yellow")
    blanco = xlwt.easyxf("pattern: pattern solid, fore_colour white")
    for i, fila in enumerate(filas, start=1):
        for j, valor in enumerate(fila):
            if valor is not None:
                hoja.write(i - 1, j, valor, amarillo if i in resaltadas else blanco)
            elif i in resaltadas:
                hoja.write(i - 1, j, "", amarillo)
    libro.save(str(ruta))
    return ruta


_CATALOGO_REAL = [
    ["CLASIFICACION ESTADISTICA INTERNACIONAL DE ENFERMEDADES"],  # fila 1: título
    ["COD_3", "DESRIPCION CATEGORIAS DE TRES CARACTERES", "COD_4", "DESCRIPCION CODIGOS DE CUATRO CARACTERES"],
    ["K02", "CARIES DENTAL", "K020", "CARIES LIMITADA AL ESMALTE"],  # fila 3: resaltada (categoría K02)
    [None, None, "K021", "CARIES DE LA DENTINA"],  # hereda la marca de su categoría
    ["A06", "AMEBIASIS", "A065\u2020", "ABSCESO AMEBIANO DEL PULMON"],  # † = doble clasificación
    ["S00", "TRAUMATISMO SUPERFICIAL DE LA CABEZA", "S000", "TRAUMATISMO DEL CUERO CABELLUDO"],
    [None, None, "S005", "TRAUMATISMO SUPERFICIAL DEL LABIO"],  # fila 7: resaltada sola (sin COD_3)
    [None, None, "S007", "TRAUMATISMOS SUPERFICIALES MULTIPLES"],
    ["G14", "SINDROME POSTPOLIO", "G14", None],  # categoría sin subdivisión y sin descripción de 4
]


def test_xls_con_relleno_errata_en_encabezado_dagas_y_herencia_de_categoria(tmp_path):
    lectura = leer_catalogo(_xls(tmp_path / "c.xls", _CATALOGO_REAL, resaltadas={3, 7}))
    filas = {f.cod_4: f for f in lectura.filas}
    assert not lectura.rechazos and len(filas) == 7
    assert {c for c, f in filas.items() if f.es_odontologico} == {"K020", "K021", "S005"}
    assert "A065" in filas  # sin la daga
    assert (filas["K021"].cod_3, filas["K021"].descripcion_3) == ("K02", "CARIES DENTAL")
    assert (filas["S005"].cod_3, filas["S005"].descripcion_3) == ("S00", "TRAUMATISMO SUPERFICIAL DE LA CABEZA")
    assert filas["G14"].descripcion_4 == "SINDROME POSTPOLIO"


def test_sin_herencia_solo_cuentan_las_filas_marcadas(tmp_path):
    ruta = _xls(tmp_path / "c.xls", _CATALOGO_REAL, resaltadas={3, 7})
    marcados = {f.cod_4 for f in leer_catalogo(ruta, herencia_categoria=False).filas if f.es_odontologico}
    assert marcados == {"K020", "S005"}


def test_xls_sin_ninguna_marca_se_rechaza(tmp_path):
    with pytest.raises(ErrorFormato, match="resaltada"):
        leer_catalogo(_xls(tmp_path / "c.xls", _CATALOGO_REAL))


def test_xlsx_con_relleno_de_color_marca_pero_el_blanco_no(tmp_path):
    ruta = tmp_path / "c.xlsx"
    libro = Workbook()
    hoja = libro.active
    for fila in [["COD_4", "DESCRIPCION"], ["K021", "Caries"], ["C187", "Colon"]]:
        hoja.append(fila)
    hoja["A2"].fill = PatternFill("solid", fgColor="FFFF00")
    hoja["A3"].fill = PatternFill("solid", fgColor="FFFFFF")
    libro.save(ruta)
    filas = {f.cod_4: f.es_odontologico for f in leer_catalogo(ruta).filas}
    assert filas == {"K021": True, "C187": False}
