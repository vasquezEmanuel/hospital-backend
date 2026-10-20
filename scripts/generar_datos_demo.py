"""Genera archivos SINTÉTICOS para probar el ETL y hacer demos. Carpeta: scripts/.

Los nombres, documentos y códigos son inventados: NO son datos reales de pacientes (el repositorio es público).
Uso (desde la raíz del repo):  python -m scripts.generar_datos_demo
Crea:  datos_demo/catalogo_cie10_demo.xlsx  y  datos_demo/atenciones_demo.xlsx
"""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

# (COD_3, descripción 3, COD_4, descripción 4, ¿odontológico?)
CATALOGO_DEMO = [
    ("K02", "Caries dental", "K021", "Caries de la dentina", True),
    ("K05", "Gingivitis y enfermedades periodontales", "K050", "Gingivitis aguda", True),
    ("K05", "Gingivitis y enfermedades periodontales", "K051", "Gingivitis crónica", True),
    ("K08", "Otros trastornos de los dientes y de sus estructuras de sostén", "K083", "Raíz dentaria retenida", True),
    ("K12", "Estomatitis y lesiones afines", "K123", "Mucositis oral (ulcerativa)", True),
    ("C18", "Tumor maligno del colon", "C187", "Tumor maligno del colon sigmoide", False),
    ("C50", "Tumor maligno de la mama", "C509", "Tumor maligno de la mama, parte no especificada", False),
    ("S72", "Fractura del fémur", "S723", "Fractura de la diáfisis del fémur", False),
    (
        "T88",
        "Otras complicaciones de la atención médica y quirúrgica",
        "T887",
        "Efecto adverso de droga o medicamento",
        False,
    ),
]

ENCABEZADOS_ATENCIONES = [
    "FECHA DE LA ATENCIÓN", "ASEGURADORA", "DOCUMENTO DE IDENTIDAD", "NOMBRE", "UBICACIÓN",
    "DIAGNÓSTICO DE HOSPITALIZACIÓN", "DIAGNÓSTICO BUCAL 1", "DIAGNÓSTICO BUCAL 2", "DIAGNÓSTICO BUCAL 3",
    "PLAN DE TRATAMIENTO", "PROFESIONAL", "OBSERVACIONES",
]  # fmt: skip

_R1 = [datetime(2026, 9, 12), "SURA", "1.025.847.210", "María Rodríguez", "Consulta externa 3", "C187", "K021",
       "Gingivitis aguda", None, "Operatoria · RX · CP · DTT", "Dra. Laura Castaño",
       "Paciente tolera el procedimiento sin complicaciones."]  # fmt: skip

# Cada fila ilustra un caso: las 5 últimas con problema deben ir a la cola de revisión.
ATENCIONES_DEMO = [
    _R1,
    ["11/09/2026", "Nueva EPS", 79421880, "Carlos Gómez", "Hospitalización piso 4",
     "C509 - Tumor maligno de la mama, parte no especificada", "K05.1", None, None, "Control de placa bacteriana",
     "Dr. Andrés Mejía", None],
    [datetime(2026, 9, 10), "Sanitas", "52880143", "Ana Martínez", "Consulta externa 1", "S723",
     "K123 Mucositis oral (ulcerativa)", None, None, "Seguimiento de mucositis en 15 días", "Dra. Laura Castaño", None],
    ["2026-09-09", "SURA", "1017442019", "Luis Herrera", "Urgencias", "T887", "Raíz dentaria retenida", None, None,
     "Exodoncia", "Dr. Andrés Mejía", "Remitido a cirugía oral."],
    [datetime(2026, 9, 8), "Coosalud", "43701882", "Diana Restrepo", "Consulta externa 2", None, "K021, K051", None,
     None, "Operatoria", "Dra. Laura Castaño", None],
    list(_R1),  # repetida: se omite (no duplica la atención)
    [datetime(2026, 8, 20), "  sura ", 79421880, "Carlos  Gómez", "Consulta externa 1", None, "Gingivitis crónica",
     None, None, "Profilaxis", "Dr. Andrés Mejía", None],
    # --- casos con problema ---
    [datetime(2026, 9, 7), "SURA", "12", "Marta Gil", None, None, "K021", None, None, None, None, None],
    ["ayer", "SURA", "55667788", "Raúl Díaz", None, None, "K021", None, None, None, None, None],
    [datetime(2026, 9, 6), "Sanitas", "98765432", "Pedro Pérez", None, None, "caries??", None, None, None, None, None],
    [datetime(2026, 9, 5), "SURA", "1020304050", "Sofía Ruiz", None, None, "C187", None, None, None, None, None],
    [datetime(2026, 9, 4), "Nueva EPS", "71234567", "Juan Torres", None, "ZZZ9", "K021", None, None, None, None, None],
]  # fmt: skip


def crear_catalogo_demo(ruta) -> Path:
    """XLSX del catálogo: los códigos odontológicos llevan el COD_4 subrayado, como en el archivo real."""
    libro = Workbook()
    hoja = libro.active
    hoja.append(["COD_3", "DESCRIPCION", "COD_4", "DESCRIPCION"])
    for cod_3, desc_3, cod_4, desc_4, odontologico in CATALOGO_DEMO:
        hoja.append([cod_3, desc_3, cod_4, desc_4])
        if odontologico:
            hoja.cell(row=hoja.max_row, column=3).font = Font(underline="single")
    return _guardar(libro, ruta)


def crear_atenciones_demo(ruta) -> Path:
    libro = Workbook()
    hoja = libro.active
    hoja.append(ENCABEZADOS_ATENCIONES)
    for fila in ATENCIONES_DEMO:
        hoja.append(fila)
    return _guardar(libro, ruta)


def _guardar(libro: Workbook, ruta) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
    return ruta


if __name__ == "__main__":
    carpeta = Path("datos_demo")
    print("Creado:", crear_catalogo_demo(carpeta / "catalogo_cie10_demo.xlsx"))
    print("Creado:", crear_atenciones_demo(carpeta / "atenciones_demo.xlsx"))