"""Esquemas de atenciones. Carpeta: app/schemas — Sprint 7.

Reglas 2 y 3: cada diagnóstico bucal lleva 1+ códigos CIE-10 odontológicos; a lo sumo un diagnóstico de
hospitalización por atención. Los identificadores que salen y entran son UUID (S6); catálogos usan su id entero.
"""

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.expediente import AtencionExpediente


def _codigo(v: str) -> str:
    limpio = v.replace(".", "").strip().upper()
    if not (3 <= len(limpio) <= 10) or not limpio.isalnum():
        raise ValueError(f"Código CIE-10 inválido: {v!r}")
    return limpio


class DiagnosticoHospitalarioIn(BaseModel):
    descripcion_original: str = Field(min_length=2, max_length=2000, examples=["Neoplasia maligna de colon sigmoide"])
    cod_4: str | None = Field(default=None, examples=["C187"], description="Cualquier código CIE-10 (regla 2)")

    @field_validator("cod_4")
    @classmethod
    def _cod(cls, v: str | None) -> str | None:
        return _codigo(v) if v else None


class DiagnosticoBucalIn(BaseModel):
    descripcion: str = Field(min_length=2, max_length=2000, examples=["Caries de la dentina"])
    codigos: list[str] = Field(min_length=1, max_length=10, description="Códigos CIE-10 odontológicos (regla 2)")

    @field_validator("codigos")
    @classmethod
    def _codigos(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(_codigo(c) for c in v))


class AtencionCreate(BaseModel):
    id_paciente: UUID
    fecha_atencion: date
    hora_atencion: time | None = None
    id_aseguradora: int | None = None
    ubicacion: str | None = Field(default=None, max_length=150)
    id_profesional: int | None = None
    profesional_texto: str | None = Field(default=None, max_length=150)
    plan_tratamiento: str | None = Field(default=None, max_length=5000)
    observaciones: str | None = Field(default=None, max_length=5000)
    ids_tratamientos: list[int] = Field(default_factory=list, max_length=30)
    diagnostico_hospitalario: DiagnosticoHospitalarioIn | None = None
    diagnosticos_bucales: list[DiagnosticoBucalIn] = Field(default_factory=list, max_length=10)

    @field_validator("fecha_atencion")
    @classmethod
    def _no_futura(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("La fecha de la atención no puede ser futura")
        return v


class PacienteResumen(BaseModel):
    id_paciente: UUID
    codigo: str = Field(examples=["P-001"])
    nombre: str
    documento_identidad: str


class AtencionListItem(BaseModel):
    """Fila de la tabla 'Atenciones'."""

    id_atencion: UUID
    codigo_atencion: str = Field(examples=["A001"], description="ID visible (solo para mostrar)")
    fecha_atencion: date
    hora_atencion: time | None = None
    paciente: PacienteResumen
    aseguradora: str | None = None
    profesional: str | None = None
    diagnostico_hospitalario: str | None = Field(default=None, description="Código CIE-10 o texto original")
    diagnosticos_bucales: list[str] = Field(description="Descripciones de los diagnósticos bucales")
    total_imagenes: int


class AtencionDetalle(AtencionExpediente):
    """Detalle de una atención: todo lo del expediente + paciente."""

    paciente: PacienteResumen
