"""Tipos compartidos por los lectores y el cargador. Carpeta: etl/ — Sprint 2, Fase 3 del documento técnico."""

from dataclasses import dataclass


class ErrorFormato(Exception):
    """El archivo no tiene la estructura esperada (encabezados faltantes, formato no soportado)."""


@dataclass(frozen=True)
class Rechazo:
    """Fila que no pudo cargarse. Va a importacion_fila para revisión manual: en la Fase 3 nada se descarta."""

    numero_fila: int  # número de fila en el archivo original (1 = primera fila)
    motivo: str
    datos: dict  # fila original tal como vino, serializable a JSON
