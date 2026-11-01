"""Lector de la hoja de atenciones (XLSX o CSV). Carpeta: etl/ — Sprint 2, Fase 3 (extracción y validación).

Entidades: paciente, atencion, diagnostico_hospitalario, diagnostico_bucal (schema.sql). Solo valida lo que no
necesita la base de datos (documento, fecha, nombre, largos). El cruce de diagnósticos contra el catálogo CIE-10
y de aseguradora/profesional contra sus catálogos lo hace el cargador. Las filas con problemas se devuelven como
Rechazo (nunca se descartan en silencio). Columnas reales de la fuente: ver sección 3 del prompt del proyecto.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from etl.archivos import leer_tabla, texto, texto_libre
from etl.comunes import ErrorFormato, Rechazo
from etl.normalizar import clave_texto, normalizar_documento, parsear_fecha, vacio

_ALIAS = {
    "fecha": ("FECHA DE LA ATENCION", "FECHA ATENCION", "FECHA"),
    "aseguradora": ("ASEGURADORA",),
    "documento": ("DOCUMENTO DE IDENTIDAD", "DOCUMENTO", "IDENTIFICACION"),
    "nombre": ("NOMBRE", "NOMBRE DEL PACIENTE", "PACIENTE"),
    "ubicacion": ("UBICACION",),
    "dx_hospitalario": ("DIAGNOSTICO DE HOSPITALIZACION", "DIAGNOSTICO HOSPITALARIO"),
    "plan": ("PLAN DE TRATAMIENTO",),
    "profesional": ("PROFESIONAL",),
    "observaciones": ("OBSERVACIONES",),
}
_BUCAL = re.compile(r"^DIAGNOSTICO BUCAL ?(\d+)?$")
_OBLIGATORIAS = {"fecha": "FECHA DE LA ATENCIÓN", "documento": "DOCUMENTO DE IDENTIDAD", "nombre": "NOMBRE"}
_MAX_FILAS_ENCABEZADO = 15
_MAX_TEXTO = 150  # largo de nombre, aseguradora, ubicación y profesional en schema.sql


@dataclass(frozen=True)
class FilaAtencion:
    numero_fila: int
    fecha: date
    documento: str
    nombre: str
    aseguradora: str | None
    ubicacion: str | None
    dx_hospitalario: str | None
    dx_bucales: list[tuple[int, str]]  # (número de columna DIAGNÓSTICO BUCAL, texto original)
    plan: str | None
    profesional: str | None
    observaciones: str | None
    crudo: dict  # fila original, para la cola de revisión


@dataclass
class LecturaAtenciones:
    filas: list[FilaAtencion] = field(default_factory=list)
    rechazos: list[Rechazo] = field(default_factory=list)


def _ubicar_columnas(fila) -> tuple[dict[str, int], list[tuple[int, int]]]:
    claves = [clave_texto(c) if not vacio(c) else "" for c in fila]
    columnas: dict[str, int] = {}
    for campo, alias in _ALIAS.items():
        for i, clave in enumerate(claves):
            if clave in alias:
                columnas[campo] = i
                break
    bucales = []  # (número, índice de columna)
    for i, clave in enumerate(claves):
        m = _BUCAL.match(clave)
        if m:
            bucales.append((int(m.group(1) or len(bucales) + 1), i))
    return columnas, sorted(bucales)


def _valor(fila, columnas: dict[str, int], campo: str):
    i = columnas.get(campo)
    return fila[i] if i is not None and i < len(fila) else None


def leer_atenciones(ruta) -> LecturaAtenciones:
    filas, _ = leer_tabla(ruta)
    indice_encabezado, columnas, bucales = None, {}, []
    for i, fila in enumerate(filas[:_MAX_FILAS_ENCABEZADO]):
        columnas, bucales = _ubicar_columnas(fila)
        if "documento" in columnas and "fecha" in columnas:
            indice_encabezado = i
            break
    if indice_encabezado is None:
        raise ErrorFormato(
            f"No se encontró el encabezado de la hoja de atenciones en las primeras {_MAX_FILAS_ENCABEZADO} filas. "
            "Se esperan, como mínimo, las columnas: " + ", ".join(_OBLIGATORIAS.values()) + "."
        )
    faltantes = [nombre for campo, nombre in _OBLIGATORIAS.items() if campo not in columnas]
    if faltantes:
        raise ErrorFormato("Faltan columnas obligatorias: " + ", ".join(faltantes) + ".")

    encabezado = filas[indice_encabezado]
    lectura = LecturaAtenciones()
    for i in range(indice_encabezado + 1, len(filas)):
        fila = filas[i]
        if all(vacio(v) for v in fila):
            continue
        numero = i + 1
        crudo = {f"{j + 1}:{texto(h)}": texto(v) for j, (h, v) in enumerate(zip(encabezado, fila, strict=False))}
        motivos: list[str] = []

        fecha = None
        bruto = _valor(fila, columnas, "fecha")
        if vacio(bruto):
            motivos.append("Falta la fecha de la atención")
        else:
            try:
                fecha = parsear_fecha(bruto)
            except ValueError:
                motivos.append(f"Fecha de la atención no reconocida: {texto(bruto)!r}")

        documento = ""
        bruto = _valor(fila, columnas, "documento")
        if vacio(bruto):
            motivos.append("Falta el documento de identidad")
        else:
            try:
                documento = normalizar_documento(texto(bruto))
            except ValueError as exc:
                motivos.append(f"Documento de identidad inválido ({texto(bruto)!r}): {exc}")

        nombre = texto(_valor(fila, columnas, "nombre"))
        if not nombre:
            motivos.append("Falta el nombre del paciente")

        campos = {c: texto(_valor(fila, columnas, c)) or None for c in ("aseguradora", "ubicacion", "profesional")}
        for etiqueta, valor in (("nombre", nombre), *campos.items()):
            if valor and len(valor) > _MAX_TEXTO:
                motivos.append(f"El campo {etiqueta} supera {_MAX_TEXTO} caracteres")

        if motivos:
            lectura.rechazos.append(Rechazo(numero, "; ".join(motivos), crudo))
            continue
        lectura.filas.append(
            FilaAtencion(
                numero_fila=numero,
                fecha=fecha,
                documento=documento,
                nombre=nombre,
                aseguradora=campos["aseguradora"],
                ubicacion=campos["ubicacion"],
                dx_hospitalario=texto(_valor(fila, columnas, "dx_hospitalario")) or None,
                dx_bucales=[
                    (n, texto(fila[c])) for n, c in bucales if c < len(fila) and not vacio(fila[c]) and texto(fila[c])
                ],
                plan=texto_libre(_valor(fila, columnas, "plan")) or None,
                profesional=campos["profesional"],
                observaciones=texto_libre(_valor(fila, columnas, "observaciones")) or None,
                crudo=crudo,
            )
        )
    return lectura
