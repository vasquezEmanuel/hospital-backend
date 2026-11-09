"""Esquemas de la búsqueda por enfermedad. Carpeta: app/schemas — Sprint 4.

Pantalla 'Diagnósticos': se busca un código CIE-10 y se listan los pacientes relacionados, uno por atención, con su
diagnóstico bucal y sus imágenes ('Consultar imágenes').
"""

from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.expediente import CodigoCie10
from app.schemas.imagen import ImagenOut


class Ambito(StrEnum):
    hospitalizacion = "hospitalizacion"
    bucal = "bucal"
    cualquiera = "cualquiera"


class EnfermedadPacienteOut(BaseModel):
    id_paciente: UUID
    codigo_paciente: str = Field(description="ID visible, p. ej. P-007")
    documento_identidad: str
    nombre: str
    id_atencion: UUID
    fecha_atencion: date
    coincide_en: list[Literal["hospitalizacion", "bucal"]] = Field(
        description="Dónde aparece el código en esa atención: diagnóstico de hospitalización y/o diagnóstico bucal"
    )
    diagnostico_hospitalario: str | None = None
    diagnosticos_bucales: list[str] = Field(description="Todos los diagnósticos bucales activos de la atención")
    total_imagenes: int = Field(description="Imágenes activas del paciente")
    imagenes: list[ImagenOut] = Field(description="Las más recientes (máximo max_imagenes), con enlace firmado")


class PacientesPorEnfermedadOut(BaseModel):
    codigo: CodigoCie10
    items: list[EnfermedadPacienteOut]
    total: int = Field(description="Atenciones que cumplen la búsqueda")
    page: int
    page_size: int
