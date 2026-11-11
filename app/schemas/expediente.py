"""Esquemas del expediente del paciente. Carpeta: app/schemas — Sprint 3.

Responde la búsqueda "por paciente -> enfermedades e imágenes" del problema que resuelve el sistema.
"""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel

from app.schemas.imagen import ImagenOut
from app.schemas.paciente import PacienteOut


class CodigoCie10(BaseModel):
    cod_4: str
    descripcion: str
    es_odontologico: bool


class DiagnosticoHospitalarioOut(BaseModel):
    descripcion_original: str
    codigo: CodigoCie10 | None = None


class DiagnosticoBucalOut(BaseModel):
    id_diagnostico_bucal: UUID
    descripcion: str
    codigos: list[CodigoCie10]
    codificado: bool  # False = solo texto, pendiente de codificar a CIE-10


class TratamientoOut(BaseModel):
    id_tratamiento: int
    nombre: str


class AtencionExpediente(BaseModel):
    id_atencion: UUID
    codigo_atencion: str  # ID visible "A001" (solo para mostrar)
    fecha_atencion: date
    hora_atencion: time | None = None
    aseguradora: str | None = None
    ubicacion: str | None = None
    profesional: str | None = None
    plan_tratamiento: str | None = None
    observaciones: str | None = None
    registrada_en: datetime
    diagnostico_hospitalario: DiagnosticoHospitalarioOut | None = None
    diagnosticos_bucales: list[DiagnosticoBucalOut]
    tratamientos: list[TratamientoOut] = []
    imagenes: list[ImagenOut]


class ExpedienteOut(BaseModel):
    paciente: PacienteOut
    atenciones: list[AtencionExpediente]
    imagenes_sin_atencion: list[ImagenOut]
    total_imagenes: int
