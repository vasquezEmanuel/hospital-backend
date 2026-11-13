"""Reportes e inicio. Carpeta: app/services — Sprint 9 (pantallas 'Reportes', 'Reporte' e 'Inicio').

Ocho tipos de reporte (los de la pantalla). Cada fila trae cantidad y porcentaje sobre la suma de las filas del reporte.
Los reportes son agregados: no exponen datos individuales de pacientes. El PDF lo genera el front desde la vista previa
(sin librería de PDF en el backend); el Excel se genera aquí con openpyxl.
"""

import io
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from app.repositories import reporte_repo as repo
from app.repositories.reporte_repo import Filtros
from app.schemas.reporte import (
    ConteoInicio,
    FilaReporte,
    FiltrosReporte,
    Reporte,
    ResumenInicio,
    TipoReporte,
    TotalesInicio,
    TotalesReporte,
)
from app.services import atencion_service
from app.services.enfermedad_service import normalizar_codigo
from app.services.errors import DatosInvalidosError, NotFoundError

LIMITE_FILAS = 200

# tipo -> (título, función, columna principal, columna secundaria)
TIPOS: dict[str, tuple[str, object, str, str | None]] = {
    "total_atenciones": ("Total de atenciones odontológicas", repo.total_atenciones, "Concepto", None),
    "atenciones_por_aseguradora": ("Atenciones por aseguradora", repo.por_aseguradora, "Aseguradora", None),
    "atenciones_por_diagnostico_hospitalario": (
        "Atenciones por diagnóstico hospitalario",
        repo.por_dx_hospitalario,
        "Diagnóstico hospitalario",
        None,
    ),
    "distribucion_diagnosticos_bucales": (
        "Distribución de diagnósticos bucales",
        repo.distribucion_bucales,
        "Diagnóstico bucal",
        None,
    ),
    "tratamientos_registrados": ("Tratamientos registrados", repo.tratamientos, "Tratamiento", None),
    "atenciones_por_profesional": ("Atenciones por profesional", repo.por_profesional, "Profesional", None),
    "registros_por_fecha": ("Registros por fecha", repo.por_fecha, "Fecha", None),
    "relacion_hospitalario_bucal": (
        "Relación entre diagnóstico hospitalario y diagnóstico bucal",
        repo.relacion_hospitalario_bucal,
        "Diagnóstico hospitalario",
        "Diagnóstico bucal",
    ),
}


def tipos() -> list[TipoReporte]:
    return [TipoReporte(tipo=k, titulo=v[0]) for k, v in TIPOS.items()]


def _porcentaje(cantidad: int, total: int) -> float:
    return round(cantidad * 100 / total, 1) if total else 0.0


def _hallazgo(tipo: str, filas: list[FilaReporte]) -> str | None:
    if tipo == "total_atenciones" or not filas:
        return None
    cima = max(filas, key=lambda f: f.cantidad)
    pct = f"{cima.porcentaje:.1f}".replace(".", ",")
    if tipo == "registros_por_fecha":
        return f"El día con más atenciones fue {cima.etiqueta}: {cima.cantidad} ({pct} % del periodo)."
    nombre = cima.etiqueta if not cima.etiqueta_secundaria else f"{cima.etiqueta} con {cima.etiqueta_secundaria}"
    return f"{nombre} concentra el {pct} % de los registros del periodo."


def generar(
    db: Session,
    tipo: str,
    *,
    fecha_desde=None,
    fecha_hasta=None,
    id_aseguradora: int | None = None,
    cod_4: str | None = None,
    id_profesional: int | None = None,
) -> Reporte:
    if tipo not in TIPOS:
        raise NotFoundError("Tipo de reporte no existe")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise DatosInvalidosError("La fecha inicial no puede ser posterior a la final")
    cod = normalizar_codigo(cod_4) if cod_4 else None
    f = Filtros(fecha_desde, fecha_hasta, id_aseguradora, cod, id_profesional)
    titulo, consulta, col1, col2 = TIPOS[tipo]
    bruto = consulta(db, f, LIMITE_FILAS)
    truncado = len(bruto) > LIMITE_FILAS
    bruto = bruto[:LIMITE_FILAS]
    suma = sum(c for _, _, c in bruto)
    filas = [
        FilaReporte(etiqueta=e or "—", etiqueta_secundaria=s, cantidad=c, porcentaje=_porcentaje(c, suma))
        for e, s, c in bruto
    ]
    pacientes, atenciones, imagenes = repo.totales(db, f)
    return Reporte(
        tipo=tipo,
        titulo=titulo,
        generado_en=datetime.now(UTC),
        filtros=FiltrosReporte(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            id_aseguradora=id_aseguradora,
            cod_4=cod,
            id_profesional=id_profesional,
        ),
        totales=TotalesReporte(pacientes=pacientes, atenciones=atenciones, imagenes=imagenes),
        columna_principal=col1,
        columna_secundaria=col2,
        filas=filas,
        hallazgo=_hallazgo(tipo, filas),
        truncado=truncado,
    )


def _seguro(valor):
    """Evita que Excel interprete como fórmula un texto que vino de datos importados (=, +, -, @)."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


def a_excel(r: Reporte) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte"
    negrita = Font(bold=True)
    hoja.append([r.titulo])
    hoja["A1"].font = Font(bold=True, size=14)
    hoja.append(["Hospital Alma Mater · Gestión odontológica"])
    hoja.append(["Generado", r.generado_en.strftime("%Y-%m-%d %H:%M UTC")])
    periodo = f"{r.filtros.fecha_desde or 'inicio'} — {r.filtros.fecha_hasta or 'hoy'}"
    hoja.append(["Periodo", periodo])
    hoja.append(["Pacientes", r.totales.pacientes, "Atenciones", r.totales.atenciones, "Imágenes", r.totales.imagenes])
    if r.hallazgo:
        hoja.append(["Hallazgo principal", _seguro(r.hallazgo)])
    hoja.append([])
    encabezado = [r.columna_principal] + ([r.columna_secundaria] if r.columna_secundaria else [])
    encabezado += ["Cantidad", "Porcentaje (%)"]
    hoja.append(encabezado)
    for celda in hoja[hoja.max_row]:
        celda.font = negrita
    for fila in r.filas:
        valores = [_seguro(fila.etiqueta)] + ([_seguro(fila.etiqueta_secundaria)] if r.columna_secundaria else [])
        hoja.append(valores + [fila.cantidad, fila.porcentaje])
    if r.truncado:
        hoja.append([f"Se muestran las primeras {LIMITE_FILAS} filas."])
    hoja.column_dimensions["A"].width = 52
    hoja.column_dimensions["B"].width = 34
    hoja.column_dimensions["C"].width = 14
    hoja.column_dimensions["D"].width = 16
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def nombre_archivo(r: Reporte) -> str:
    desde = r.filtros.fecha_desde or "inicio"
    hasta = r.filtros.fecha_hasta or "hoy"
    return f"reporte_{r.tipo}_{desde}_{hasta}.xlsx"


def resumen_inicio(db: Session) -> ResumenInicio:
    f = Filtros()
    pacientes, atenciones, imagenes = repo.totales(db, f)
    aseg = repo.por_aseguradora(db, f, 5)[:5]
    bucales = repo.distribucion_bucales(db, f, 5)[:5]
    ultimas = atencion_service.listar(
        db,
        page=1,
        page_size=5,
        q=None,
        cod_4=None,
        id_paciente=None,
        id_aseguradora=None,
        fecha_desde=None,
        fecha_hasta=None,
    )
    return ResumenInicio(
        totales=TotalesInicio(
            pacientes=pacientes, atenciones=atenciones, imagenes=imagenes, diagnosticos=repo.diagnosticos_distintos(db)
        ),
        atenciones_por_aseguradora=[ConteoInicio(etiqueta=e, cantidad=c) for e, _, c in aseg],
        diagnosticos_bucales_frecuentes=[ConteoInicio(etiqueta=e, cantidad=c) for e, _, c in bucales],
        ultimas_atenciones=ultimas.items,
    )


__all__ = ["a_excel", "generar", "nombre_archivo", "resumen_inicio", "tipos"]
