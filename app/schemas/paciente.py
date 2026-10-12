"""Esquemas de paciente. Pantallas 'Pacientes', 'Nuevo paciente' y ficha del paciente."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TipoDocumento = Literal["CC", "TI", "RC", "CE", "PA", "PE", "PT"]
Sexo = Literal["M", "F", "O"]

_DOC_SEPARATORS = re.compile(r"[.\s-]")
_DOC_VALID = re.compile(r"^[A-Z0-9]{4,20}$")
_PHONE_VALID = re.compile(r"^[0-9+\s()-]{7,20}$")


def normalizar_documento(valor: str) -> str:
    """'1.025.847.210' -> '1025847210'. El front muestra puntos; la BD guarda solo el valor limpio."""
    limpio = _DOC_SEPARATORS.sub("", valor).upper()
    if not _DOC_VALID.match(limpio):
        raise ValueError("Documento inválido: use 4 a 20 caracteres alfanuméricos")
    return limpio


class _PacienteCampos(BaseModel):
    @field_validator("fecha_nacimiento", check_fields=False)
    @classmethod
    def _no_futura(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return v

    @field_validator("telefono", check_fields=False)
    @classmethod
    def _telefono(cls, v: str | None) -> str | None:
        if v is not None and not _PHONE_VALID.match(v):
            raise ValueError("Teléfono inválido")
        return v


class PacienteCreate(_PacienteCampos):
    tipo_documento: TipoDocumento
    documento_identidad: str = Field(examples=["1.025.847.210"])
    nombre: str = Field(min_length=3, max_length=150, examples=["María Rodríguez"])
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    ciudad: str | None = Field(default=None, max_length=100)

    @field_validator("documento_identidad")
    @classmethod
    def _doc(cls, v: str) -> str:
        return normalizar_documento(v)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return " ".join(v.split())


class PacienteUpdate(_PacienteCampos):
    """'Editar información'. El documento de identidad NO es editable (regla 1: es la identidad)."""

    tipo_documento: TipoDocumento | None = None
    nombre: str | None = Field(default=None, min_length=3, max_length=150)
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    ciudad: str | None = Field(default=None, max_length=100)


class PacienteListItem(BaseModel):
    """Fila de la tabla 'Pacientes'."""

    id_paciente: int
    codigo: str = Field(examples=["P-001"], description="ID visible en el front, derivado de id_paciente")
    tipo_documento: str | None
    documento_identidad: str
    nombre: str
    total_atenciones: int
    ultima_atencion: date | None


class PacienteOut(BaseModel):
    """Ficha del paciente. Los conteos de diagnósticos e imágenes llegan en Sprint 3 (/expediente)."""

    model_config = ConfigDict(from_attributes=True)

    id_paciente: int
    codigo: str
    tipo_documento: str | None
    documento_identidad: str
    nombre: str
    fecha_nacimiento: date | None
    edad: int | None
    sexo: str | None
    telefono: str | None
    correo: str | None
    ciudad: str | None
    aseguradora_actual: str | None = Field(description="Aseguradora de la última atención")
    total_atenciones: int
    ultima_atencion: date | None
    creado_en: datetime
